use anyhow::{bail, Context, Result};
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use crate::sparse;

const RKFW_MAGIC: &[u8; 4] = b"RKFW";
const AFP_MAGIC_RKAF: &[u8; 4] = b"RKAF";
const AFP_MAGIC_RKAS: &[u8; 4] = b"RKAS";

const AFP_ENTRY_SIZE: usize = 0x48; // 72 bytes

/// Check if a file looks like a Rockchip RKFW image.
pub fn probe(data: &[u8]) -> bool {
    data.len() >= 4 && &data[0..4] == RKFW_MAGIC
}

struct AfpEntry {
    name: String,
    offset: u32,
    size: u32,
}

fn read_null_terminated(buf: &[u8]) -> String {
    let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
    String::from_utf8_lossy(&buf[..end]).to_string()
}

fn parse_afp_entry(buf: &[u8]) -> Result<AfpEntry> {
    if buf.len() < AFP_ENTRY_SIZE {
        bail!("AFP entry buffer too small");
    }
    let name = read_null_terminated(&buf[0x00..0x20]);
    let offset = u32::from_le_bytes(buf[0x20..0x24].try_into()?);
    // 0x24..0x28 is padding/user data
    let size = u32::from_le_bytes(buf[0x28..0x2C].try_into()?);

    Ok(AfpEntry { name, offset, size })
}

/// Strip A/B slot suffix: *_a → *
fn strip_ab_suffix(name: &str) -> String {
    if let Some(base) = name.strip_suffix("_a.img") {
        format!("{base}.img")
    } else if let Some(base) = name.strip_suffix("_b.img") {
        format!("{base}.img")
    } else {
        name.to_string()
    }
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let mut f = File::open(input).context("failed to open Rockchip image")?;

    // Parse RKFW header
    let mut rkfw_header = [0u8; 0x24];
    f.read_exact(&mut rkfw_header)?;

    if &rkfw_header[0..4] != RKFW_MAGIC {
        bail!("not an RKFW image: bad magic");
    }

    let firmware_offset = u32::from_le_bytes(rkfw_header[0x1C..0x20].try_into()?) as u64;
    let firmware_size = u32::from_le_bytes(rkfw_header[0x20..0x24].try_into()?) as u64;

    if firmware_size == 0 {
        bail!("RKFW firmware size is 0");
    }

    // Seek to firmware.img (AFP container)
    f.seek(SeekFrom::Start(firmware_offset))?;

    // Read AFP header
    let mut afp_header = [0u8; 0x4C];
    f.read_exact(&mut afp_header)?;

    // Validate AFP magic
    let afp_magic = &afp_header[0..4];
    if afp_magic != AFP_MAGIC_RKAF && afp_magic != AFP_MAGIC_RKAS {
        bail!(
            "not an AFP container: bad magic {:?}",
            &afp_header[0..4]
        );
    }

    let entry_count = u32::from_le_bytes(afp_header[0x44..0x48].try_into()?) as usize;
    if entry_count == 0 || entry_count > 1024 {
        bail!("invalid AFP entry count: {entry_count}");
    }

    // Read entry table
    let mut entries = Vec::with_capacity(entry_count);
    let mut entry_buf = [0u8; AFP_ENTRY_SIZE];
    for _ in 0..entry_count {
        f.read_exact(&mut entry_buf)?;
        entries.push(parse_afp_entry(&entry_buf)?);
    }

    let mut extracted = Vec::new();

    for entry in &entries {
        if entry.size == 0 || entry.name.is_empty() {
            continue;
        }

        // AFP offsets are relative to the AFP container start
        let abs_offset = firmware_offset + entry.offset as u64;
        f.seek(SeekFrom::Start(abs_offset))?;

        // Determine output filename — sanitize path to prevent traversal
        let raw_name = if entry.name.contains('.') {
            entry.name.clone()
        } else {
            format!("{}.img", entry.name)
        };
        let out_name = strip_ab_suffix(&raw_name);
        let safe_name = Path::new(&out_name)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| format!("partition_{}.img", extracted.len()));
        let out_path = output_dir.join(&safe_name);

        // Stream copy
        let mut out_file = File::create(&out_path)?;
        let mut remaining = entry.size as u64;
        let mut buf = vec![0u8; 8 * 1024 * 1024];
        while remaining > 0 {
            let to_read = remaining.min(buf.len() as u64) as usize;
            f.read_exact(&mut buf[..to_read])?;
            out_file.write_all(&buf[..to_read])?;
            remaining -= to_read as u64;
        }
        drop(out_file);

        let _ = sparse::maybe_unsparse(&out_path);
        extracted.push(out_path);
    }

    Ok(extracted)
}

#[pyfunction]
#[pyo3(name = "rockchip")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results
        .into_iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect())
}
