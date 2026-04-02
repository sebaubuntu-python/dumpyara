use anyhow::{Context, Result};
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use quick_xml::de::from_str;
use serde::Deserialize;
use std::collections::BTreeMap;
use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use crate::sparse;

/// A single <program> entry from rawprogram*.xml.
#[derive(Debug, Deserialize)]
struct Program {
    #[serde(default)]
    filename: String,
    #[serde(default)]
    label: String,
    #[serde(default)]
    num_partition_sectors: u64,
    #[serde(default)]
    start_sector: u64,
    #[serde(default)]
    file_sector_offset: u64,
    #[serde(default, rename = "SECTOR_SIZE_IN_BYTES")]
    sector_size: Option<u64>,
}

/// Root element wrapping <program> entries.
#[derive(Debug, Deserialize)]
struct Data {
    #[serde(rename = "program", default)]
    programs: Vec<Program>,
}

/// Check if a zip archive contains rawprogram*.xml (QFIL format).
pub fn probe_zip(archive: &zip::ZipArchive<File>) -> bool {
    (0..archive.len()).any(|i| {
        archive.name_for_index(i).map_or(false, |n| {
            let base = Path::new(n)
                .file_name()
                .map(|f| f.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            base.starts_with("rawprogram") && base.ends_with(".xml")
        })
    })
}

/// Resolve a filename from rawprogram XML against the temp directory.
/// Tries the full path first, then falls back to just the basename,
/// since zip extraction flattens all entries to their basenames.
fn resolve_file(temp_dir: &Path, filename: &str) -> Option<PathBuf> {
    // Try verbatim first
    let full = temp_dir.join(filename);
    if full.is_file() {
        return Some(full);
    }
    // Fall back to basename (handles "images/system.img" → "system.img")
    let base = Path::new(filename).file_name()?;
    let flat = temp_dir.join(base);
    if flat.is_file() {
        return Some(flat);
    }
    None
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let zip_file = File::open(input).context("failed to open QFIL zip")?;
    let mut archive = zip::ZipArchive::new(zip_file).context("failed to read zip archive")?;

    // Extract all files to a temp directory (flattened to basenames)
    let temp_dir = output_dir.join("_qfil_temp");
    fs::create_dir_all(&temp_dir)?;

    for i in 0..archive.len() {
        let mut entry = archive.by_index(i)?;
        if entry.is_dir() {
            continue;
        }

        let entry_name = entry.name().to_string();
        let base_name = Path::new(&entry_name)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or(entry_name.clone());

        let out_path = temp_dir.join(&base_name);
        let mut out_file = File::create(&out_path)?;
        std::io::copy(&mut entry, &mut out_file)?;
    }

    // Find and parse rawprogram XML
    let rawprogram_xml = find_rawprogram_xml(&temp_dir)?;
    let xml_content = fs::read_to_string(&rawprogram_xml)
        .context("failed to read rawprogram XML")?;

    let data: Data = from_str(&xml_content)
        .context("failed to parse rawprogram XML")?;

    // Group programs by label so that multi-chunk partitions (sparsechunk
    // entries listed as separate <program> elements with the same label)
    // are merged instead of overwriting each other.
    let mut label_groups: BTreeMap<String, Vec<&Program>> = BTreeMap::new();
    for program in &data.programs {
        if program.filename.is_empty() || program.label.is_empty() {
            continue;
        }
        if program.num_partition_sectors == 0 {
            continue;
        }
        label_groups
            .entry(program.label.clone())
            .or_default()
            .push(program);
    }

    let mut extracted = Vec::new();

    for (label, programs) in &label_groups {
        // Sanitize label to prevent path traversal from crafted XML
        let safe_label = Path::new(label)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| format!("partition_{}", extracted.len()));
        let out_name = format!("{safe_label}.img");
        let out_path = output_dir.join(&out_name);

        let default_sector_size: u64 = 512;

        if programs.len() == 1 {
            let program = programs[0];
            let sector_size = program.sector_size.unwrap_or(default_sector_size);

            if let Some(src) = resolve_file(&temp_dir, &program.filename) {
                // Honor file_sector_offset: read from the specified offset
                if program.file_sector_offset > 0 && program.num_partition_sectors > 0 {
                    let offset = program.file_sector_offset * sector_size;
                    let length = program.num_partition_sectors * sector_size;
                    copy_range(&src, &out_path, offset, length)?;
                } else {
                    fs::copy(&src, &out_path)?;
                }
            } else {
                // No direct file — try finding sparsechunks by label
                let chunks = find_sparse_chunks(&temp_dir, &program.filename, label);
                if chunks.is_empty() {
                    continue;
                }
                write_chunks(&chunks, &out_path)?;
            }
        } else {
            // Multiple program entries for the same label.
            // Sort by start_sector so chunks are in the right order.
            let mut sorted: Vec<&Program> = programs.clone();
            sorted.sort_by_key(|p| p.start_sector);

            // Check if all entries reference the same backing file
            let all_same_file = sorted.windows(2).all(|w| w[0].filename == w[1].filename);

            if all_same_file {
                // Same backing file — extract each slice at its offset
                let src = match resolve_file(&temp_dir, &sorted[0].filename) {
                    Some(s) => s,
                    None => continue,
                };
                let mut out_file = File::create(&out_path)?;
                for p in &sorted {
                    let ss = p.sector_size.unwrap_or(default_sector_size);
                    let offset = p.file_sector_offset * ss;
                    let length = p.num_partition_sectors * ss;
                    let mut f = File::open(&src)?;
                    f.seek(SeekFrom::Start(offset))?;
                    let mut remaining = length;
                    let mut buf = vec![0u8; 8 * 1024 * 1024];
                    while remaining > 0 {
                        let to_read = remaining.min(buf.len() as u64) as usize;
                        let n = f.read(&mut buf[..to_read])?;
                        if n == 0 {
                            break;
                        }
                        out_file.write_all(&buf[..n])?;
                        remaining -= n as u64;
                    }
                }
            } else {
                // Distinct files per entry — collect and merge
                let files: Vec<PathBuf> = sorted
                    .iter()
                    .filter_map(|p| resolve_file(&temp_dir, &p.filename))
                    .collect();

                if files.is_empty() {
                    let p0 = sorted[0];
                    let chunks = find_sparse_chunks(&temp_dir, &p0.filename, label);
                    if chunks.is_empty() {
                        continue;
                    }
                    write_chunks(&chunks, &out_path)?;
                } else {
                    write_chunks(&files, &out_path)?;
                }
            }
        }

        let _ = sparse::maybe_unsparse(&out_path);
        extracted.push(out_path);
    }

    // Clean up temp directory
    let _ = fs::remove_dir_all(&temp_dir);

    Ok(extracted)
}

/// Copy `length` bytes from `src` starting at `offset` into a new file at `dst`.
fn copy_range(src: &Path, dst: &Path, offset: u64, length: u64) -> Result<()> {
    let mut f = File::open(src)?;
    f.seek(SeekFrom::Start(offset))?;
    let mut out = File::create(dst)?;
    let mut remaining = length;
    let mut buf = vec![0u8; 8 * 1024 * 1024];
    while remaining > 0 {
        let to_read = remaining.min(buf.len() as u64) as usize;
        let n = f.read(&mut buf[..to_read])?;
        if n == 0 {
            break;
        }
        out.write_all(&buf[..n])?;
        remaining -= n as u64;
    }
    Ok(())
}

/// Write a list of chunk files to an output path.
/// If the first chunk is Android sparse, use the sparse decoder to merge.
/// Otherwise, concatenate raw bytes.
fn write_chunks(chunks: &[PathBuf], out_path: &Path) -> Result<()> {
    if sparse::check_sparse(&chunks[0]) {
        let paths: Vec<&Path> = chunks.iter().map(|p| p.as_path()).collect();
        sparse::convert_sparse_chunks_to_raw(&paths, out_path)?;
    } else {
        let mut out_file = File::create(out_path)?;
        for chunk in chunks {
            let mut f = File::open(chunk)?;
            std::io::copy(&mut f, &mut out_file)?;
        }
    }
    Ok(())
}

/// Find the rawprogram XML file in the temp directory.
/// Prefers rawprogram_unsparse0.xml over other variants.
fn find_rawprogram_xml(dir: &Path) -> Result<PathBuf> {
    let preferred = dir.join("rawprogram_unsparse0.xml");
    if preferred.is_file() {
        return Ok(preferred);
    }

    for entry in fs::read_dir(dir)? {
        let entry = entry?;
        let name = entry.file_name().to_string_lossy().to_lowercase();
        if name.starts_with("rawprogram") && name.ends_with(".xml") {
            return Ok(entry.path());
        }
    }

    anyhow::bail!("no rawprogram*.xml found in archive");
}

/// Find sparse chunk files for a given partition.
/// Tries both the XML filename stem and label-based patterns.
fn find_sparse_chunks(dir: &Path, filename: &str, label: &str) -> Vec<PathBuf> {
    let stem = Path::new(filename)
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default();

    let patterns = [
        format!("{stem}_sparsechunk."),
        format!("{stem}.img_sparsechunk."),
        format!("{label}_sparsechunk."),
        format!("{label}.img_sparsechunk."),
    ];

    if let Ok(entries) = fs::read_dir(dir) {
        let mut matching: Vec<PathBuf> = entries
            .filter_map(|e| e.ok())
            .filter(|e| {
                let name = e.file_name().to_string_lossy().to_string();
                patterns.iter().any(|p| name.starts_with(p))
            })
            .map(|e| e.path())
            .collect();

        // Sort by chunk index (the number after the last dot)
        matching.sort_by_key(|p| {
            p.extension()
                .and_then(|e| e.to_str())
                .and_then(|e| e.parse::<u32>().ok())
                .unwrap_or(0)
        });

        if !matching.is_empty() {
            return matching;
        }
    }

    Vec::new()
}

#[pyfunction]
#[pyo3(name = "qfil")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results
        .into_iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect())
}
