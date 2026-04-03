use anyhow::{bail, Context, Result};
use flate2::read::GzDecoder;
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::io::{BufReader, Cursor, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use crate::sparse;

/// Sony sparse chunk type identifiers.
const CAC_RAW: u16 = 0xCAC1;
const CAC_FILL: u16 = 0xCAC2;
const CAC_DONT_CARE: u16 = 0xCAC3;
const CAC_CRC: u16 = 0xCAC4;
const CAC_SKIP: u16 = 0xCAC5;

/// Block size used by Sony sparse format.
const SONY_BLOCK_SIZE: u32 = 4096;

#[derive(Debug)]
enum SinVersion {
    V3,
    V4,
    V5,
    LegacySSSS,
    LegacyOther,
}

/// Detect SIN version from header bytes.
fn detect_version(data: &[u8]) -> Option<SinVersion> {
    if data.len() < 4 {
        return None;
    }
    if &data[0..3] == b"SIN" {
        return match data[3] {
            0x03 => Some(SinVersion::V3),
            0x04 => Some(SinVersion::V4),
            0x05 => Some(SinVersion::V5),
            _ => None,
        };
    }
    if &data[0..4] == b"SSSS" {
        return Some(SinVersion::LegacySSSS);
    }
    // BFBF or other legacy
    if data.len() > 0x4040 {
        return Some(SinVersion::LegacyOther);
    }
    None
}

/// Check if raw data starts with a SIN or legacy header.
pub fn probe(data: &[u8]) -> bool {
    if data.len() < 4 {
        return false;
    }
    &data[0..3] == b"SIN"
        || &data[0..4] == b"SSSS"
        || (data[0] == 0xBF && data[1] == 0xBF)
}

/// Reassemble Sony sparse chunks into a raw image.
/// The input is the raw chunk data (after gzip/tar extraction).
fn reassemble_sony_sparse(data: &[u8], output: &mut File) -> Result<()> {
    let mut pos = 0;

    while pos + 12 <= data.len() {
        let chunk_type = u16::from_le_bytes(data[pos..pos + 2].try_into()?);
        // Validate chunk type
        if !matches!(chunk_type, CAC_RAW | CAC_FILL | CAC_DONT_CARE | CAC_CRC | CAC_SKIP) {
            // Not a Sony sparse chunk — treat remaining data as raw
            output.write_all(&data[pos..])?;
            break;
        }

        let chunk_blocks = u32::from_le_bytes(data[pos + 4..pos + 8].try_into()?);
        let chunk_data_len = u32::from_le_bytes(data[pos + 8..pos + 12].try_into()?) as usize;
        pos += 12;

        match chunk_type {
            CAC_RAW => {
                if pos + chunk_data_len > data.len() {
                    bail!("Sony sparse raw chunk extends beyond data");
                }
                output.write_all(&data[pos..pos + chunk_data_len])?;
                pos += chunk_data_len;
            }
            CAC_FILL => {
                if chunk_data_len < 4 || pos + chunk_data_len > data.len() {
                    bail!("Sony sparse fill chunk invalid");
                }
                let fill_val = &data[pos..pos + 4];
                let fill_block = fill_val.repeat(SONY_BLOCK_SIZE as usize / 4);
                for _ in 0..chunk_blocks {
                    output.write_all(&fill_block)?;
                }
                pos += chunk_data_len;
            }
            CAC_DONT_CARE | CAC_SKIP => {
                // Write zeros for the specified size
                let zeros = vec![0u8; SONY_BLOCK_SIZE as usize];
                for _ in 0..chunk_blocks {
                    output.write_all(&zeros)?;
                }
                pos += chunk_data_len;
            }
            CAC_CRC => {
                // Skip CRC chunk data
                pos += chunk_data_len;
            }
            _ => {
                pos += chunk_data_len;
            }
        }
    }

    Ok(())
}

/// Write tar entry data to output, handling Sony sparse if detected.
fn write_entry_data(entry_data: &[u8], output: &mut File) -> Result<()> {
    if entry_data.len() >= 2 {
        let first_u16 = u16::from_le_bytes(entry_data[0..2].try_into().unwrap_or([0, 0]));
        if matches!(first_u16, CAC_RAW | CAC_FILL | CAC_DONT_CARE | CAC_CRC | CAC_SKIP) {
            reassemble_sony_sparse(entry_data, output)?;
            return Ok(());
        }
    }
    output.write_all(entry_data)?;
    Ok(())
}

/// Extract SIN v3/v4 data: gzip → tar → Sony sparse → raw.
fn extract_sin_v3_v4(data: &[u8], output: &mut File) -> Result<()> {
    // Find the start of gzip data (skip the SIN header)
    // SIN header varies in size; scan for gzip magic 0x1F 0x8B
    let gz_start = find_gzip_start(data).context("no gzip data found in SIN v3/v4")?;

    let decoder = GzDecoder::new(&data[gz_start..]);
    let mut archive = tar::Archive::new(decoder);

    // Process each tar entry individually to preserve boundaries
    for entry in archive.entries()? {
        let mut entry = entry?;
        if entry.size() == 0 {
            continue;
        }
        let mut entry_data = Vec::with_capacity(entry.size().min(256 * 1024 * 1024) as usize);
        entry.read_to_end(&mut entry_data)?;
        write_entry_data(&entry_data, output)?;
    }

    Ok(())
}

/// Extract SIN v5 data: tar (no gzip) → Sony sparse → raw.
fn extract_sin_v5(data: &[u8], output: &mut File) -> Result<()> {
    // Skip SIN header, find tar data
    let tar_start = find_tar_start(data).context("no tar data found in SIN v5")?;

    let mut archive = tar::Archive::new(Cursor::new(&data[tar_start..]));

    // Process each tar entry individually to preserve boundaries
    for entry in archive.entries()? {
        let mut entry = entry?;
        if entry.size() == 0 {
            continue;
        }
        let mut entry_data = Vec::with_capacity(entry.size().min(256 * 1024 * 1024) as usize);
        entry.read_to_end(&mut entry_data)?;
        write_entry_data(&entry_data, output)?;
    }

    Ok(())
}

/// Extract legacy SIN with SSSS header.
fn extract_legacy_ssss(data: &[u8], output: &mut File) -> Result<()> {
    if data.len() < 64 {
        bail!("SSSS data too small");
    }
    let lo = u16::from_le_bytes(data[60..62].try_into()?) as usize;
    let hi = u16::from_le_bytes(data[62..64].try_into()?) as usize;
    let payload_size = hi * 65536 + lo;
    let offset = 64;

    if offset + payload_size > data.len() {
        bail!("SSSS payload extends beyond file");
    }

    output.write_all(&data[offset..offset + payload_size])?;
    Ok(())
}

/// Extract legacy SIN with BFBF or unknown header.
fn extract_legacy_other(data: &[u8], output: &mut File) -> Result<()> {
    if data.len() <= 0x4040 {
        bail!("legacy SIN data too small");
    }
    output.write_all(&data[0x4040..])?;
    Ok(())
}

/// Find gzip magic (0x1F 0x8B) in data.
fn find_gzip_start(data: &[u8]) -> Option<usize> {
    for i in 0..data.len().saturating_sub(1) {
        if data[i] == 0x1F && data[i + 1] == 0x8B {
            return Some(i);
        }
    }
    None
}

/// Find tar header — look for "ustar" at offset 257.
fn find_tar_start(data: &[u8]) -> Option<usize> {
    // Tar blocks are 512 bytes; "ustar" appears at offset 257 within a tar header
    for offset in (0..data.len().saturating_sub(512)).step_by(512) {
        if offset + 262 <= data.len() && &data[offset + 257..offset + 262] == b"ustar" {
            return Some(offset);
        }
    }
    // If no ustar found, try byte-by-byte (some SIN variants have odd alignment)
    for i in 0..data.len().saturating_sub(262) {
        if &data[i + 257..i + 262] == b"ustar" {
            return Some(i);
        }
    }
    None
}

/// Extract a single SIN file to a raw image.
fn extract_sin_data(data: &[u8], out_path: &Path) -> Result<()> {
    let version = detect_version(data).context("cannot detect SIN version")?;

    let mut out_file = File::create(out_path)?;
    match version {
        SinVersion::V3 | SinVersion::V4 => extract_sin_v3_v4(data, &mut out_file)?,
        SinVersion::V5 => extract_sin_v5(data, &mut out_file)?,
        SinVersion::LegacySSSS => extract_legacy_ssss(data, &mut out_file)?,
        SinVersion::LegacyOther => extract_legacy_other(data, &mut out_file)?,
    }
    drop(out_file);

    // Convert Android sparse if needed
    let _ = sparse::maybe_unsparse(out_path);

    Ok(())
}

/// Extract an FTF file (zip containing .sin files).
fn extract_ftf(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let zip_file = File::open(input)?;
    let mut archive = zip::ZipArchive::new(zip_file)?;

    let mut extracted = Vec::new();

    // Collect .sin entry indices and names
    let sin_entries: Vec<(usize, String)> = (0..archive.len())
        .filter_map(|i| {
            let name = archive.by_index(i).ok()?.name().to_string();
            if name.to_lowercase().ends_with(".sin") {
                Some((i, name))
            } else {
                None
            }
        })
        .collect();

    for (idx, name) in sin_entries {
        let mut entry = archive.by_index(idx)?;
        let mut data = Vec::with_capacity(entry.size() as usize);
        entry.read_to_end(&mut data)?;

        let base_name = Path::new(&name)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or(name.clone());
        // Replace .sin with .img (case-insensitive — detection accepts any case)
        let out_name = if base_name.to_lowercase().ends_with(".sin") {
            format!("{}.img", &base_name[..base_name.len() - 4])
        } else {
            base_name
        };
        let out_path = output_dir.join(&out_name);

        match extract_sin_data(&data, &out_path) {
            Ok(()) => extracted.push(out_path),
            Err(_) => {
                // Skip unrecognized .sin entries (e.g. non-SIN files with .sin extension)
                let _ = std::fs::remove_file(&out_path);
            }
        }
    }

    Ok(extracted)
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    // Check if this is an FTF (zip containing .sin files)
    if let Ok(zip_file) = File::open(input) {
        if let Ok(archive) = zip::ZipArchive::new(zip_file) {
            let has_sin = (0..archive.len()).any(|i| {
                archive
                    .name_for_index(i)
                    .map(|n| n.to_lowercase().ends_with(".sin"))
                    .unwrap_or(false)
            });
            if has_sin {
                return extract_ftf(input, output_dir);
            }
        }
    }

    // Direct SIN file — stream-scan for gzip/tar offset instead of
    // reading the entire file into memory (avoids OOM on multi-GB files).
    let stem = input
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| "output".to_string());
    let out_path = output_dir.join(format!("{stem}.img"));

    let mut f = File::open(input)?;
    let file_size = f.metadata()?.len();

    // Read the header (first 4KB is more than enough for any SIN header)
    let header_cap = file_size.min(4096) as usize;
    let mut header = vec![0u8; header_cap];
    f.read_exact(&mut header)?;

    let version = detect_version(&header);
    match version {
        Some(SinVersion::V3) | Some(SinVersion::V4) => {
            // Scan header region for gzip magic, then stream from that offset
            let gz_start = find_gzip_start(&header)
                .context("no gzip data found in SIN v3/v4 header")?;
            f.seek(SeekFrom::Start(gz_start as u64))?;
            let decoder = GzDecoder::new(BufReader::new(f));
            let mut archive = tar::Archive::new(decoder);
            let mut out_file = File::create(&out_path)?;
            for entry in archive.entries()? {
                let mut entry = entry?;
                if entry.size() == 0 {
                    continue;
                }
                let mut entry_data =
                    Vec::with_capacity(entry.size().min(256 * 1024 * 1024) as usize);
                entry.read_to_end(&mut entry_data)?;
                write_entry_data(&entry_data, &mut out_file)?;
            }
            drop(out_file);
            let _ = sparse::maybe_unsparse(&out_path);
        }
        Some(SinVersion::V5) => {
            // Scan header for tar "ustar" signature, then stream from that offset
            let tar_start = find_tar_start(&header)
                .context("no tar data found in SIN v5 header")?;
            f.seek(SeekFrom::Start(tar_start as u64))?;
            let mut archive = tar::Archive::new(BufReader::new(f));
            let mut out_file = File::create(&out_path)?;
            for entry in archive.entries()? {
                let mut entry = entry?;
                if entry.size() == 0 {
                    continue;
                }
                let mut entry_data =
                    Vec::with_capacity(entry.size().min(256 * 1024 * 1024) as usize);
                entry.read_to_end(&mut entry_data)?;
                write_entry_data(&entry_data, &mut out_file)?;
            }
            drop(out_file);
            let _ = sparse::maybe_unsparse(&out_path);
        }
        Some(SinVersion::LegacySSSS) | Some(SinVersion::LegacyOther) => {
            // Legacy formats have small headers — safe to read fully
            let mut data = header;
            f.read_to_end(&mut data)?;
            extract_sin_data(&data, &out_path)?;
        }
        None => {
            bail!("cannot detect SIN version");
        }
    }

    Ok(vec![out_path])
}

/// Check if a zip archive is an FTF (contains .sin files).
pub fn probe_zip(archive: &zip::ZipArchive<File>) -> bool {
    (0..archive.len()).any(|i| {
        archive
            .name_for_index(i)
            .map(|n| n.to_lowercase().ends_with(".sin"))
            .unwrap_or(false)
    })
}

#[pyfunction]
#[pyo3(name = "sin")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results
        .into_iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect())
}
