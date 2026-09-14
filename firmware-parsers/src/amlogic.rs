use anyhow::{bail, Context, Result};
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

use crate::sparse;

const AML_MAGIC: u32 = 0x27051956;
const HEADER_SIZE: usize = 0x40;
const ITEM_SIZE: usize = 0x240;

/// Check if a file looks like an Amlogic USB Burning Tool image.
pub fn probe(data: &[u8]) -> bool {
    data.len() >= 4 && u32::from_be_bytes(data[0..4].try_into().unwrap()) == AML_MAGIC
}

struct AmlItem {
    offset: u64,
    file_size: u64,
    extension: String,
    name: String,
}

fn read_null_terminated(buf: &[u8]) -> String {
    let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
    String::from_utf8_lossy(&buf[..end]).to_string()
}

fn parse_item(buf: &[u8]) -> Result<AmlItem> {
    if buf.len() < ITEM_SIZE {
        bail!("Amlogic item buffer too small");
    }
    // offset at 0x10 (big-endian u32), file_size at 0x18 (big-endian u32)
    let offset = u32::from_be_bytes(buf[0x10..0x14].try_into()?) as u64;
    let file_size = u32::from_be_bytes(buf[0x18..0x1C].try_into()?) as u64;
    let extension = read_null_terminated(&buf[0x20..0x40]);
    let name = read_null_terminated(&buf[0x120..0x140]);

    Ok(AmlItem {
        offset,
        file_size,
        extension,
        name,
    })
}

/// Apply Amlogic-specific output name renaming rules.
fn rename_output(name: &str, ext: &str) -> String {
    let raw_name = format!("{name}.{ext}");

    // *.PARTITION → *.img
    if ext.eq_ignore_ascii_case("PARTITION") {
        let img_name = format!("{name}.img");
        // Strip _a suffix (A/B slot)
        if let Some(base) = img_name.strip_suffix("_a.img") {
            return format!("{base}.img");
        }
        return img_name;
    }

    // *_aml_dtb.img → dtb.img
    if raw_name.ends_with("_aml_dtb.img") || raw_name.ends_with("_aml_dtb.PARTITION") {
        return "dtb.img".to_string();
    }

    // Strip _a suffix
    if let Some(base) = raw_name.strip_suffix("_a.img") {
        return format!("{base}.img");
    }

    raw_name
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    // Check if it's a tar.bz2 wrapper — if so, decompress first
    let data_path = maybe_unwrap_tar_bz2(input, output_dir)?;
    let actual_input = data_path.as_deref().unwrap_or(input);

    let mut f = File::open(actual_input).context("failed to open Amlogic image")?;

    // Read and validate header
    let mut header = [0u8; HEADER_SIZE];
    f.read_exact(&mut header)?;

    let magic = u32::from_be_bytes(header[0..4].try_into()?);
    if magic != AML_MAGIC {
        bail!("not an Amlogic image: bad magic 0x{magic:08X}");
    }

    let item_count = u32::from_be_bytes(header[0x14..0x18].try_into()?) as usize;
    if item_count == 0 || item_count > 1024 {
        bail!("invalid Amlogic item count: {item_count}");
    }

    // Read item table
    let mut items = Vec::with_capacity(item_count);
    let mut item_buf = vec![0u8; ITEM_SIZE];
    for _ in 0..item_count {
        f.read_exact(&mut item_buf)?;
        items.push(parse_item(&item_buf)?);
    }

    let mut extracted = Vec::new();

    for item in &items {
        if item.file_size == 0 || item.name.is_empty() {
            continue;
        }

        let raw_name = rename_output(&item.name, &item.extension);
        // Sanitize: strip path components to prevent directory traversal
        let out_name = Path::new(&raw_name)
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_else(|| format!("partition_{}.img", extracted.len()));
        let out_path = output_dir.join(&out_name);

        f.seek(SeekFrom::Start(item.offset))?;

        // Stream copy
        let mut out_file = File::create(&out_path)?;
        let mut remaining = item.file_size;
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

    // Clean up temp decompressed file if we had a tar.bz2 wrapper
    if let Some(tmp) = data_path {
        let _ = std::fs::remove_file(&tmp);
    }

    Ok(extracted)
}

/// If the input is a bzip2-compressed tar, decompress it and return the path
/// to the inner .img. Detection is content-based (bzip2 magic "BZh") to match
/// how detect.rs identifies tar.bz2-wrapped Amlogic images.
fn maybe_unwrap_tar_bz2(input: &Path, output_dir: &Path) -> Result<Option<PathBuf>> {
    // Check content for bzip2 magic rather than relying on filename extension,
    // since detect.rs identifies these by content.
    let mut f = File::open(input)?;
    let mut magic = [0u8; 3];
    if f.read_exact(&mut magic).is_err() || &magic != b"BZh" {
        return Ok(None);
    }
    drop(f);

    let f = File::open(input)?;
    let decoder = bzip2::read::BzDecoder::new(f);
    let mut archive = tar::Archive::new(decoder);

    for entry in archive.entries()? {
        let mut entry = entry?;
        let entry_path = entry.path()?.into_owned();
        let entry_name = entry_path
            .file_name()
            .map(|n| n.to_string_lossy().into_owned())
            .unwrap_or_default();

        if entry_name.ends_with(".img") {
            // Verify Amlogic magic before accepting — archives may contain
            // non-Amlogic .img files (readmes, configs) before the real payload.
            let mut magic = [0u8; 4];
            if entry.read_exact(&mut magic).is_err() {
                continue;
            }
            if u32::from_be_bytes(magic) != AML_MAGIC {
                continue;
            }
            // Rewind isn't possible on tar entries, so write magic + rest
            let tmp_path = output_dir.join(format!("_aml_tmp_{entry_name}"));
            let mut out = File::create(&tmp_path)?;
            out.write_all(&magic)?;
            std::io::copy(&mut entry, &mut out)?;
            return Ok(Some(tmp_path));
        }
    }

    Ok(None)
}

#[pyfunction]
#[pyo3(name = "amlogic")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results
        .into_iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect())
}
