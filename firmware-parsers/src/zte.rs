use anyhow::{Context, Result};
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use regex::Regex;
use std::collections::BTreeMap;
use std::fs::File;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use crate::sparse;

#[derive(Debug, Clone, Copy)]
pub enum ZteMode {
    PChunks,
    Bin,
}

fn p_suffix_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)^([^/]*?)-p(\d+)$").unwrap())
}

/// Check if a zip archive is a ZTE update.zip.
/// Returns the detected mode or None.
pub fn probe_zip(archive: &zip::ZipArchive<File>) -> Option<ZteMode> {
    let re = p_suffix_regex();

    let mut has_p_suffix = false;
    let mut has_bin = false;

    for i in 0..archive.len() {
        if let Some(name) = archive.name_for_index(i) {
            let base = Path::new(name)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();

            if re.is_match(&base) {
                has_p_suffix = true;
            }
            if base.ends_with(".bin") && is_partition_name(&base) {
                has_bin = true;
            }
        }
    }

    if has_p_suffix {
        return Some(ZteMode::PChunks);
    }
    if has_bin {
        return Some(ZteMode::Bin);
    }
    None
}

/// Check if a filename looks like a known partition name.
pub fn is_partition_name(name: &str) -> bool {
    let lower = name.to_lowercase();
    let stem = lower
        .strip_suffix(".bin")
        .or_else(|| lower.strip_suffix(".img"))
        .unwrap_or(&lower);
    matches!(
        stem,
        "system"
            | "vendor"
            | "boot"
            | "recovery"
            | "modem"
            | "userdata"
            | "cache"
            | "dtbo"
            | "vbmeta"
            | "vbmeta_system"
            | "vbmeta_vendor"
            | "super"
            | "product"
            | "system_ext"
            | "system_other"
            | "odm"
            | "odm_dlkm"
            | "vendor_dlkm"
            | "vendor_boot"
            | "init_boot"
            | "metadata"
            | "persist"
            | "splash"
            | "aboot"
            | "preloader"
            | "lk"
            | "logo"
            | "tz"
            | "sbl1"
            | "rpm"
            | "hyp"
            | "pmic"
            | "abl"
            | "xbl"
            | "devcfg"
            | "cmnlib"
            | "cmnlib64"
            | "keymaster"
            | "sec"
    )
}

/// Extract p-suffix chunk mode: concatenate system-p00, system-p01, ... → system.img
fn extract_p_chunks(
    archive: &mut zip::ZipArchive<File>,
    output_dir: &Path,
) -> Result<Vec<PathBuf>> {
    let re = p_suffix_regex();

    // Group entries by partition name — use name_for_index to avoid decompression
    let mut partitions: BTreeMap<String, Vec<(u32, usize)>> = BTreeMap::new();

    for i in 0..archive.len() {
        if let Some(name) = archive.name_for_index(i) {
            let base = Path::new(name)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();

            if let Some(caps) = re.captures(&base) {
                let partition = caps.get(1).unwrap().as_str().to_lowercase();
                let chunk_idx: u32 = caps.get(2).unwrap().as_str().parse().unwrap_or(0);
                partitions
                    .entry(partition)
                    .or_default()
                    .push((chunk_idx, i));
            }
        }
    }

    let mut extracted = Vec::new();

    for (partition, mut chunks) in partitions {
        // Sort by chunk index
        chunks.sort_by_key(|(idx, _)| *idx);

        let out_path = output_dir.join(format!("{partition}.img"));
        let mut out_file = File::create(&out_path)?;

        for (_, zip_idx) in &chunks {
            let mut entry = archive.by_index(*zip_idx)?;
            let mut buf = Vec::with_capacity(entry.size() as usize);
            entry.read_to_end(&mut buf)?;
            out_file.write_all(&buf)?;
        }
        drop(out_file);

        let _ = sparse::maybe_unsparse(&out_path);
        extracted.push(out_path);
    }

    Ok(extracted)
}

/// Extract bin mode: rename *.bin → *.img
fn extract_bin(
    archive: &mut zip::ZipArchive<File>,
    output_dir: &Path,
) -> Result<Vec<PathBuf>> {
    let mut extracted = Vec::new();

    // Collect indices first using name_for_index (avoids decompression)
    let bin_entries: Vec<(usize, String)> = (0..archive.len())
        .filter_map(|i| {
            let name = archive.name_for_index(i)?.to_string();
            let base = Path::new(&name)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();
            if base.ends_with(".bin") && is_partition_name(&base) {
                Some((i, base))
            } else {
                None
            }
        })
        .collect();

    for (idx, base_name) in bin_entries {
        let mut entry = archive.by_index(idx)?;

        let out_name = base_name.replace(".bin", ".img");
        let out_path = output_dir.join(&out_name);

        let mut out_file = File::create(&out_path)?;
        std::io::copy(&mut entry, &mut out_file)?;
        drop(out_file);

        let _ = sparse::maybe_unsparse(&out_path);
        extracted.push(out_path);
    }

    Ok(extracted)
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let zip_file = File::open(input).context("failed to open ZTE zip")?;
    let mut archive = zip::ZipArchive::new(zip_file).context("failed to read zip archive")?;

    // Detect mode from the same archive (avoid re-opening)
    let mode = probe_zip(&archive);

    match mode {
        Some(ZteMode::PChunks) => extract_p_chunks(&mut archive, output_dir),
        Some(ZteMode::Bin) => extract_bin(&mut archive, output_dir),
        None => anyhow::bail!("not a ZTE update.zip"),
    }
}

#[pyfunction]
#[pyo3(name = "zte")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results
        .into_iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect())
}
