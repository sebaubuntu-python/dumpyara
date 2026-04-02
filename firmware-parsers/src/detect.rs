use pyo3::prelude::*;
use std::fs::File;
use std::io::Read;
use std::path::Path;

use crate::{mtk_sign, nb0, pac, sparse};

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
    if pac::probe(&buf) {
        return "pac";
    }
    if sparse::check_sparse(path) {
        return "sparse";
    }
    if nb0::probe(&buf, file_size) {
        return "nb0";
    }

    // Zip-based probes — if file starts with PK magic, open the archive
    // and inspect entry names to identify the format.
    if buf[0..2] == *b"PK" {
        if let Ok(zip_file) = File::open(path) {
            if let Ok(archive) = zip::ZipArchive::new(zip_file) {
                if mtk_sign::probe_zip(&archive) {
                    return "mtk_sign";
                }
                // Phase 5: qfil, zte, kddi probes go here
            }
        }
    }

    // Additional probes added in later phases:
    // Phase 3: ozip, sin
    // Phase 4: amlogic, rockchip

    "unknown"
}

/// Python-exposed: detect the firmware format of a file.
#[pyfunction]
#[pyo3(name = "detect")]
pub fn py_detect(path: &str) -> PyResult<String> {
    Ok(probe_magic(Path::new(path)).to_string())
}
