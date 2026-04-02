use anyhow::{bail, Context, Result};
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use crate::sparse;

/// Determine the payload offset and size from a *-sign.img header.
/// Returns (offset, length) of the payload within the data.
fn strip_header(data: &[u8]) -> Result<(usize, usize)> {
    if data.len() >= 64 && &data[0..4] == b"SSSS" {
        // SSSS magic: payload size encoded in bytes 60..64
        let lo = u16::from_le_bytes(data[60..62].try_into()?) as usize;
        let hi = u16::from_le_bytes(data[62..64].try_into()?) as usize;
        let payload_size = hi * 65536 + lo;
        let offset = 64;
        if offset + payload_size > data.len() {
            bail!(
                "SSSS payload extends beyond file: offset={offset}, size={payload_size}, file={}",
                data.len()
            );
        }
        Ok((offset, payload_size))
    } else if data.len() > 0x4040 {
        // BFBF or unknown: skip first 0x4040 bytes
        let offset = 0x4040;
        let payload_size = data.len() - offset;
        Ok((offset, payload_size))
    } else {
        bail!(
            "file too small for MTK signed image ({} bytes, need > 0x4040)",
            data.len()
        );
    }
}

/// Rename "*-sign.img" to "*.img" by stripping the "-sign" suffix.
fn strip_sign_suffix(name: &str) -> String {
    if let Some(base) = name.strip_suffix("-sign.img") {
        format!("{base}.img")
    } else if let Some(base) = name.strip_suffix("-sign.IMG") {
        format!("{base}.img")
    } else {
        name.to_string()
    }
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let zip_file = File::open(input).context("failed to open MTK sign zip")?;
    let mut archive = zip::ZipArchive::new(zip_file).context("failed to read zip archive")?;

    let mut extracted = Vec::new();

    // Collect names first to avoid borrow issues
    let sign_entries: Vec<(usize, String)> = (0..archive.len())
        .filter_map(|i| {
            let name = archive.by_index(i).ok()?.name().to_string();
            let lower = name.to_lowercase();
            if lower.ends_with("-sign.img") {
                Some((i, name))
            } else {
                None
            }
        })
        .collect();

    for (idx, original_name) in sign_entries {
        let mut entry = archive.by_index(idx)?;

        // Read entire entry into memory (needed for header parsing)
        let mut data = Vec::with_capacity(entry.size() as usize);
        entry.read_to_end(&mut data)?;

        // Strip the signed header
        let (offset, len) = strip_header(&data)?;
        let payload = &data[offset..offset + len];

        // Strip path components, keep just the filename
        let base_name = Path::new(&original_name)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or(original_name.clone());
        let out_name = strip_sign_suffix(&base_name);
        let out_path = output_dir.join(&out_name);

        // Write payload
        let mut out_file = File::create(&out_path)?;
        out_file.write_all(payload)?;
        drop(out_file);

        // Convert sparse images if needed
        let _ = sparse::maybe_unsparse(&out_path);

        extracted.push(out_path);
    }

    Ok(extracted)
}

/// Check if a zip archive contains *-sign.img entries (for detection).
pub fn probe_zip(archive: &zip::ZipArchive<File>) -> bool {
    (0..archive.len()).any(|i| {
        archive
            .name_for_index(i)
            .map(|n| n.to_lowercase().ends_with("-sign.img"))
            .unwrap_or(false)
    })
}

#[pyfunction]
#[pyo3(name = "mtk_sign")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results.into_iter().map(|p| p.to_string_lossy().into_owned()).collect())
}
