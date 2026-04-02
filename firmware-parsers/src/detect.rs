use pyo3::prelude::*;
use std::fs::File;
use std::io::Read;
use std::path::Path;

use crate::{amlogic, kddi, mtk_sign, nb0, ozip, pac, qfil, rockchip, sin, zte};

/// Peek inside a bzip2-compressed tar for Amlogic magic in any entry.
/// Scans all tar members (not just the first) since packages may contain
/// readme/manifest files before the actual .img payload.
fn tar_bz2_contains_amlogic(path: &Path) -> bool {
    let f = match File::open(path) {
        Ok(f) => f,
        Err(_) => return false,
    };
    let decoder = bzip2::read::BzDecoder::new(f);
    let mut archive = tar::Archive::new(decoder);
    let mut entries = match archive.entries() {
        Ok(e) => e,
        Err(_) => return false,
    };
    while let Some(Ok(mut entry)) = entries.next() {
        if entry.size() < 4 {
            continue;
        }
        let mut magic = [0u8; 4];
        if entry.read_exact(&mut magic).is_ok()
            && u32::from_be_bytes(magic) == 0x27051956
        {
            return true;
        }
    }
    false
}

/// Read the first 64 bytes of a file and identify the format.
/// Returns the format name as a string, or "unknown".
pub fn probe_magic(path: &Path) -> &'static str {
    let Ok(mut f) = File::open(path) else {
        return "unknown";
    };
    let file_size = f.metadata().map(|m| m.len()).unwrap_or(0);
    let mut buf = [0u8; 64];
    let _ = f.read(&mut buf);

    // Magic-based probes (order matters for disambiguation)
    if ozip::probe(&buf) {
        return "ozip";
    }
    if pac::probe(&buf) {
        return "pac";
    }
    if rockchip::probe(&buf) {
        return "rockchip";
    }
    if amlogic::probe(&buf) {
        return "amlogic";
    }
    if sin::probe(&buf) {
        return "sin";
    }
    // Note: sparse images are NOT returned as a top-level format here.
    // They are handled per-file by dumpyara's raw_image.py/sparsed_images.py
    // which call sparse_to_raw() directly.

    if nb0::probe(&buf, file_size) {
        return "nb0";
    }

    // Bzip2-wrapped tar — peek inside the first entry for known magics
    if buf.len() >= 3 && &buf[0..3] == b"BZh" && tar_bz2_contains_amlogic(path) {
        return "amlogic";
    }

    // Zip-based probes — if file starts with PK magic, open the archive
    // and inspect entry names to identify the format.
    // Priority: ozip(mode2) → sin(ftf) → qfil → mtk_sign → zte → kddi
    if buf[0..2] == *b"PK" {
        if let Ok(zip_file) = File::open(path) {
            if let Ok(archive) = zip::ZipArchive::new(zip_file) {
                if ozip::probe_zip(&archive) {
                    return "ozip";
                }
                if sin::probe_zip(&archive) {
                    return "sin";
                }
                if qfil::probe_zip(&archive) {
                    return "qfil";
                }
                if mtk_sign::probe_zip(&archive) {
                    return "mtk_sign";
                }
                if zte::probe_zip(&archive).is_some() {
                    return "zte";
                }
                if kddi::probe_zip(&archive) {
                    return "kddi";
                }
            }
        }
    }

    "unknown"
}

/// Python-exposed: detect the firmware format of a file.
#[pyfunction]
#[pyo3(name = "detect")]
pub fn py_detect(path: &str) -> PyResult<String> {
    Ok(probe_magic(Path::new(path)).to_string())
}
