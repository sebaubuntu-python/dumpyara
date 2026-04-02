use anyhow::{bail, Context, Result};
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use crate::sparse;

const ENTRY_SIZE: usize = 64;

/// Check if a file looks like an NB0 container.
/// Reads file_count from first 4 bytes; sanity checks that count is
/// reasonable and the file is large enough to hold the partition table.
/// `file_size` is the total size of the file on disk.
pub fn probe(data: &[u8], file_size: u64) -> bool {
    if data.len() < 4 {
        return false;
    }
    let count = u32::from_le_bytes(data[0..4].try_into().unwrap()) as usize;
    // Sanity: count must be 1..255 and the file must be large enough for the header
    count > 0 && count < 256 && file_size >= (4 + count * ENTRY_SIZE) as u64
}

struct Nb0Entry {
    data_offset: u32,
    data_size: u32,
    filename: String,
}

fn parse_entry(buf: &[u8; ENTRY_SIZE]) -> Result<Nb0Entry> {
    let data_offset = u32::from_le_bytes(buf[0..4].try_into()?);
    let data_size = u32::from_le_bytes(buf[4..8].try_into()?);
    // bytes 8..16 are unknown fields
    let name_bytes = &buf[16..64];
    let name_end = name_bytes.iter().position(|&b| b == 0).unwrap_or(name_bytes.len());
    let filename = std::str::from_utf8(&name_bytes[..name_end])
        .context("invalid UTF-8 in NB0 entry filename")?
        .to_string();
    Ok(Nb0Entry {
        data_offset,
        data_size,
        filename,
    })
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let mut f = File::open(input).context("failed to open NB0 file")?;

    // Read file count
    let mut header = [0u8; 4];
    f.read_exact(&mut header)?;
    let count = u32::from_le_bytes(header) as usize;

    if count == 0 || count >= 256 {
        bail!("invalid NB0 file count: {count}");
    }

    // Read partition table
    let mut entries = Vec::with_capacity(count);
    let mut entry_buf = [0u8; ENTRY_SIZE];
    for _ in 0..count {
        f.read_exact(&mut entry_buf)?;
        entries.push(parse_entry(&entry_buf)?);
    }

    let data_start = (4 + count * ENTRY_SIZE) as u64;
    let mut extracted = Vec::new();

    for entry in &entries {
        if entry.data_size == 0 || entry.filename.is_empty() {
            continue;
        }

        let abs_offset = data_start + entry.data_offset as u64;
        f.seek(SeekFrom::Start(abs_offset))?;

        // Determine output filename — ensure it ends with .img
        let out_name = if entry.filename.contains('.') {
            entry.filename.clone()
        } else {
            format!("{}.img", entry.filename)
        };
        let out_path = output_dir.join(&out_name);

        // Stream copy in chunks
        let mut out_file = File::create(&out_path)?;
        let mut remaining = entry.data_size as u64;
        let mut buf = vec![0u8; 8 * 1024 * 1024]; // 8MB buffer
        while remaining > 0 {
            let to_read = remaining.min(buf.len() as u64) as usize;
            f.read_exact(&mut buf[..to_read])?;
            out_file.write_all(&mut buf[..to_read])?;
            remaining -= to_read as u64;
        }
        drop(out_file);

        // Convert sparse images if needed
        let _ = sparse::maybe_unsparse(&out_path);

        extracted.push(out_path);
    }

    Ok(extracted)
}

#[pyfunction]
#[pyo3(name = "nb0")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results.into_iter().map(|p| p.to_string_lossy().into_owned()).collect())
}
