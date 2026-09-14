use anyhow::{Context, Result};
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use crate::sparse;
use crate::zte;

fn p_suffix_regex() -> &'static regex::Regex {
    static RE: OnceLock<regex::Regex> = OnceLock::new();
    RE.get_or_init(|| regex::Regex::new(r"(?i)-p\d+$").unwrap())
}

/// Check if a zip archive is a KDDI package.
/// Distinguished from ZTE by absence of rawprogram XML and p-suffix entries.
pub fn probe_zip(archive: &zip::ZipArchive<File>) -> bool {
    let mut has_bins = false;
    let mut has_rawprogram = false;
    let mut has_p_suffix = false;

    let re = p_suffix_regex();

    for i in 0..archive.len() {
        if let Some(name) = archive.name_for_index(i) {
            let lower = name.to_lowercase();
            let base = Path::new(name)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();

            if lower.contains("rawprogram") && lower.ends_with(".xml") {
                has_rawprogram = true;
            }
            if base.ends_with(".bin") && zte::is_partition_name(&base) {
                has_bins = true;
            }
            if re.is_match(&base) {
                has_p_suffix = true;
            }
        }
    }

    has_bins && !has_rawprogram && !has_p_suffix
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let zip_file = File::open(input).context("failed to open KDDI zip")?;
    let mut archive = zip::ZipArchive::new(zip_file).context("failed to read zip archive")?;

    let mut extracted = Vec::new();

    // Collect .bin entries
    let bin_entries: Vec<(usize, String)> = (0..archive.len())
        .filter_map(|i| {
            let name = archive.name_for_index(i)?.to_string();
            let base = Path::new(&name)
                .file_name()
                .map(|n| n.to_string_lossy().into_owned())
                .unwrap_or_default();
            if base.ends_with(".bin") && zte::is_partition_name(&base) {
                Some((i, base))
            } else {
                None
            }
        })
        .collect();

    for (idx, base_name) in bin_entries {
        let mut entry = archive.by_index(idx)?;

        // Rename .bin → .img
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

#[pyfunction]
#[pyo3(name = "kddi")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results
        .into_iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect())
}
