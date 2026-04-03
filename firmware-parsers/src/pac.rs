use anyhow::{bail, Context, Result};
use encoding_rs::UTF_16LE;
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use crate::sparse;

/// PAC v2 version string "BP_R" encoded as UTF-16LE at offset 0.
const PAC_V2_MAGIC: &[u8; 8] = b"B\x00P\x00_\x00R\x00";

// PAC v2 header layout (2124 = 0x84C bytes):
//   0x000: szVersion      (44 bytes, UTF-16LE)
//   0x02C: dwHiSize       (4 bytes)
//   0x030: dwLoSize       (4 bytes)
//   0x034: productName    (512 bytes, UTF-16LE)
//   0x234: firmwareName   (512 bytes, UTF-16LE)
//   0x434: partitionCount (4 bytes)
//   0x438: partitionsListStart (4 bytes)
//   ... rest is flags/CRC
const PAC_HEADER_SIZE: usize = 0x84C;
const PARTITION_COUNT_OFFSET: usize = 0x434;
const PARTITIONS_LIST_START_OFFSET: usize = 0x438;

// File entry layout (2580 = 0xA14 bytes):
//   0x000: length         (4 bytes, should be 0xA14)
//   0x004: partitionName  (512 bytes, UTF-16LE)
//   0x204: fileName       (512 bytes, UTF-16LE)
//   0x404: szFileName     (504 bytes, UTF-16LE, reserved)
//   0x5FC: hiPartitionSize (4 bytes)
//   0x600: hiDataOffset   (4 bytes)
//   0x604: loPartitionSize (4 bytes)
//   0x608: nFileFlag      (4 bytes)
//   0x60C: nCheckFlag     (4 bytes)
//   0x610: loDataOffset   (4 bytes)
//   ... rest is padding
const ENTRY_SIZE: usize = 0xA14;

/// Check if a file looks like a Unisoc .pac container.
/// PAC v2 files start with the UTF-16LE string "BP_R" (version prefix).
pub fn probe(data: &[u8]) -> bool {
    data.len() >= 8 && &data[0..8] == PAC_V2_MAGIC
}

/// Decode a UTF-16LE null-terminated string from a fixed-size buffer.
fn decode_utf16le(buf: &[u8]) -> String {
    let (decoded, _, _) = UTF_16LE.decode(buf);
    decoded.trim_end_matches('\0').to_string()
}

struct PacEntry {
    partition_name: String,
    filename: String,
    data_offset: u64,
    partition_size: u64,
    file_flag: u32,
}

fn parse_entry(buf: &[u8]) -> Result<PacEntry> {
    if buf.len() < ENTRY_SIZE {
        bail!("PAC entry buffer too small: {} < {}", buf.len(), ENTRY_SIZE);
    }
    let partition_name = decode_utf16le(&buf[0x004..0x204]);
    let filename = decode_utf16le(&buf[0x204..0x404]);
    let hi_partition_size = u32::from_le_bytes(buf[0x5FC..0x600].try_into()?) as u64;
    let hi_data_offset = u32::from_le_bytes(buf[0x600..0x604].try_into()?) as u64;
    let lo_partition_size = u32::from_le_bytes(buf[0x604..0x608].try_into()?) as u64;
    let file_flag = u32::from_le_bytes(buf[0x608..0x60C].try_into()?);
    let lo_data_offset = u32::from_le_bytes(buf[0x610..0x614].try_into()?) as u64;

    Ok(PacEntry {
        partition_name,
        filename,
        data_offset: (hi_data_offset << 32) | lo_data_offset,
        partition_size: (hi_partition_size << 32) | lo_partition_size,
        file_flag,
    })
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let mut f = File::open(input).context("failed to open PAC file")?;

    // Read header
    let mut header = vec![0u8; PAC_HEADER_SIZE];
    f.read_exact(&mut header)?;

    if &header[0..8] != PAC_V2_MAGIC {
        bail!("not a PAC v2 file: bad version string");
    }

    let partition_count = u32::from_le_bytes(
        header[PARTITION_COUNT_OFFSET..PARTITION_COUNT_OFFSET + 4].try_into()?,
    ) as usize;
    let partitions_list_start = u32::from_le_bytes(
        header[PARTITIONS_LIST_START_OFFSET..PARTITIONS_LIST_START_OFFSET + 4].try_into()?,
    ) as u64;

    if partition_count == 0 || partition_count > 1024 {
        bail!("invalid PAC partition count: {partition_count}");
    }

    // Seek to partition table
    f.seek(SeekFrom::Start(partitions_list_start))?;

    // Read entries
    let mut entries = Vec::with_capacity(partition_count);
    let mut entry_buf = vec![0u8; ENTRY_SIZE];
    for _ in 0..partition_count {
        f.read_exact(&mut entry_buf)?;
        entries.push(parse_entry(&entry_buf)?);
    }

    let mut extracted = Vec::new();

    for entry in &entries {
        // Skip entries with no data or no file
        if entry.partition_size == 0 || entry.filename.is_empty() || entry.file_flag == 0 {
            continue;
        }

        // Sanitize output filename
        let safe_name = Path::new(&entry.filename)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| format!("{}.img", entry.partition_name));
        let out_path = output_dir.join(&safe_name);

        f.seek(SeekFrom::Start(entry.data_offset))?;

        // Stream copy
        let mut out_file = File::create(&out_path)?;
        let mut remaining = entry.partition_size;
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
