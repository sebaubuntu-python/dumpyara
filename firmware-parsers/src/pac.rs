use anyhow::{bail, Context, Result};
use encoding_rs::UTF_16LE;
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use crate::sparse;

const PAC_MAGIC: u32 = 0xFFFAFFFF;
const ENTRY_SIZE: usize = 0x184;
const PARTITION_TABLE_OFFSET: usize = 0x0110;
const ENTRY_COUNT_OFFSET: usize = 0x000C;

/// Check if a file looks like a Unisoc .pac container.
pub fn probe(data: &[u8]) -> bool {
    if data.len() < 4 {
        return false;
    }
    u32::from_le_bytes(data[0..4].try_into().unwrap()) == PAC_MAGIC
}

/// Decode a UTF-16LE null-terminated string from a fixed-size buffer.
fn decode_utf16le(buf: &[u8]) -> String {
    let (decoded, _, _) = UTF_16LE.decode(buf);
    decoded.trim_end_matches('\0').to_string()
}

struct PacEntry {
    name: String,
    filename: String,
    offset: u64,
    size: u64,
}

fn parse_entry(buf: &[u8]) -> Result<PacEntry> {
    if buf.len() < ENTRY_SIZE {
        bail!("PAC entry buffer too small");
    }
    let name = decode_utf16le(&buf[0x00..0x40]);
    let filename = decode_utf16le(&buf[0x40..0x80]);
    let offset = u32::from_le_bytes(buf[0x80..0x84].try_into()?) as u64;
    let size = u32::from_le_bytes(buf[0x84..0x88].try_into()?) as u64;
    Ok(PacEntry {
        name,
        filename,
        offset,
        size,
    })
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let mut f = File::open(input).context("failed to open PAC file")?;

    // Read header to get entry count
    let mut header = [0u8; PARTITION_TABLE_OFFSET];
    f.read_exact(&mut header)?;

    let magic = u32::from_le_bytes(header[0..4].try_into()?);
    if magic != PAC_MAGIC {
        bail!("not a PAC file: bad magic 0x{magic:08X}");
    }

    let entry_count = u32::from_le_bytes(
        header[ENTRY_COUNT_OFFSET..ENTRY_COUNT_OFFSET + 4].try_into()?,
    ) as usize;

    if entry_count == 0 || entry_count > 1024 {
        bail!("invalid PAC entry count: {entry_count}");
    }

    // Read partition table
    let mut entries = Vec::with_capacity(entry_count);
    let mut entry_buf = vec![0u8; ENTRY_SIZE];
    for _ in 0..entry_count {
        f.read_exact(&mut entry_buf)?;
        entries.push(parse_entry(&entry_buf)?);
    }

    let mut extracted = Vec::new();

    for entry in &entries {
        if entry.size == 0 || entry.filename.is_empty() {
            continue;
        }

        // Determine output filename — sanitize path to prevent traversal
        let raw_name = if entry.filename.ends_with(".img") || entry.name.is_empty() {
            entry.filename.clone()
        } else {
            format!("{}.img", entry.name)
        };
        let out_name = Path::new(&raw_name)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| format!("partition_{}.img", extracted.len()));
        let out_path = output_dir.join(&out_name);

        f.seek(SeekFrom::Start(entry.offset))?;

        // Stream copy
        let mut out_file = File::create(&out_path)?;
        let mut remaining = entry.size;
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
#[pyo3(name = "pac")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results.into_iter().map(|p| p.to_string_lossy().into_owned()).collect())
}
