use pyo3::prelude::*;
use std::fs::File;
use std::io::Read;
use std::path::Path;

use crate::sparse;

/// Read the first 64 bytes of a file and identify the format.
/// Returns the format name as a string, or "unknown".
pub fn probe_magic(path: &Path) -> &'static str {
    let Ok(mut f) = File::open(path) else {
        return "unknown";
    };
    let mut buf = [0u8; 64];
    let _ = f.read(&mut buf);

    if sparse::check_sparse(path) {
        return "sparse";
    }

    // Additional probes will be added in later phases:
    // Phase 2: nb0, pac
    // Phase 3: ozip, sin
    // Phase 4: amlogic, rockchip
    // Phase 5: qfil, zte, kddi (zip-based, need archive inspection)

    "unknown"
}

/// Python-exposed: detect the firmware format of a file.
#[pyfunction]
#[pyo3(name = "detect")]
pub fn py_detect(path: &str) -> PyResult<String> {
    Ok(probe_magic(Path::new(path)).to_string())
}
