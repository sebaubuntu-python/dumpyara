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

// AFP (RKAF) entry: name(32) + file(64) + offset(4) + flash_offset(4) + usespace(4) + size(4) = 112
const AFP_ENTRY_SIZE: usize = 0x70;
// AFP header: magic(4) + size(4) + model(64) + manufacturer(60) + version(4) + item_count(4) = 140
const AFP_HEADER_SIZE: usize = 0x8C;

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
    // Entry layout (0x70 = 112 bytes):
    //   0x00..0x20  name (32 bytes, null-terminated)
    //   0x20..0x60  file path (64 bytes, null-terminated)
    //   0x60..0x64  offset (u32 LE) — relative to AFP container start
    //   0x64..0x68  flash_offset (u32 LE)
    //   0x68..0x6C  usespace (u32 LE)
    //   0x6C..0x70  size (u32 LE)
    let name = read_null_terminated(&buf[0x00..0x20]);
    let offset = u32::from_le_bytes(buf[0x60..0x64].try_into()?);
    let size = u32::from_le_bytes(buf[0x6C..0x70].try_into()?);

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

    // Parse RKFW header (packed/unaligned layout):
    // 0x00: magic (4), 0x04: header_size (2), 0x06: version (4),
    // 0x0A: code (4), 0x0E: date (7), 0x15: chip (4),
    // 0x19: loader_offset (4), 0x1D: loader_size (4),
    // 0x21: image_offset (4), 0x25: image_size (4)
    let mut rkfw_header = [0u8; 0x29];
    f.read_exact(&mut rkfw_header)?;

    if &rkfw_header[0..4] != RKFW_MAGIC {
        bail!("not an RKFW image: bad magic");
    }

    // image_offset at 0x21, image_size at 0x25 (packed, not aligned)
    let firmware_offset = u32::from_le_bytes(rkfw_header[0x21..0x25].try_into()?) as u64;
    let firmware_size = u32::from_le_bytes(rkfw_header[0x25..0x29].try_into()?) as u64;

    if firmware_size == 0 {
        bail!("RKFW firmware size is 0");
    }

    // Seek to firmware.img (AFP container)
    f.seek(SeekFrom::Start(firmware_offset))?;

    // Read AFP header (0x8C bytes)
    let mut afp_header = [0u8; AFP_HEADER_SIZE];
    f.read_exact(&mut afp_header)?;

    // Validate AFP magic
    let afp_magic = &afp_header[0..4];
    if afp_magic != AFP_MAGIC_RKAF && afp_magic != AFP_MAGIC_RKAS {
        bail!(
            "not an AFP container: bad magic {:?}",
            &afp_header[0..4]
        );
    }

    // entry_count at offset 0x88 within AFP header
    let entry_count = u32::from_le_bytes(afp_header[0x88..0x8C].try_into()?) as usize;
    if entry_count == 0 || entry_count > 1024 {
        bail!("invalid AFP entry count: {entry_count}");
    }

    // Read entry table (each entry is 0x70 bytes)
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
