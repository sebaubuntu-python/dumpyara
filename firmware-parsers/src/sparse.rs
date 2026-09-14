use android_sparse::read::Reader;
use android_sparse::write::Decoder;
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::io::{BufReader, BufWriter, Read};
use std::path::Path;

const SPARSE_MAGIC: u32 = 0xED26FF3A;

/// Check if a file is an Android sparse image by reading the first 4 bytes.
pub fn check_sparse(path: &Path) -> bool {
    let Ok(mut f) = File::open(path) else {
        return false;
    };
    let mut buf = [0u8; 4];
    if f.read_exact(&mut buf).is_err() {
        return false;
    }
    u32::from_le_bytes(buf) == SPARSE_MAGIC
}

/// Convert an Android sparse image to a raw image.
pub fn convert_sparse_to_raw(input: &Path, output: &Path) -> anyhow::Result<()> {
    let reader = Reader::new(BufReader::new(File::open(input)?))?;

    let out_file = File::create(output)?;
    let mut decoder = Decoder::new(BufWriter::new(out_file))?;
    for block in reader {
        decoder.write_block(&block?)?;
    }
    decoder.close()?;

    Ok(())
}

/// If the file at `path` is a sparse image, convert it to raw in-place.
/// Returns true if conversion happened.
pub fn maybe_unsparse(path: &Path) -> anyhow::Result<bool> {
    if !check_sparse(path) {
        return Ok(false);
    }

    let tmp = path.with_extension("raw.tmp");
    convert_sparse_to_raw(path, &tmp)?;
    std::fs::rename(&tmp, path)?;
    Ok(true)
}

/// Convert multiple sparse chunk files into a single raw image.
pub fn convert_sparse_chunks_to_raw(inputs: &[&Path], output: &Path) -> anyhow::Result<()> {
    let out_file = File::create(output)?;
    let mut decoder = Decoder::new(BufWriter::new(out_file))?;
    for input in inputs {
        let reader = Reader::new(BufReader::new(File::open(input)?))?;
        for block in reader {
            decoder.write_block(&block?)?;
        }
    }
    decoder.close()?;
    Ok(())
}

/// Python-exposed: convert a sparse image to a raw image.
#[pyfunction]
#[pyo3(name = "sparse_to_raw")]
pub fn py_sparse_to_raw(input: &str, output: &str) -> PyResult<()> {
    convert_sparse_to_raw(Path::new(input), Path::new(output))
        .map_err(|e| PyIOError::new_err(e.to_string()))
}

/// Python-exposed: convert multiple sparse chunk files into a single raw image.
#[pyfunction]
#[pyo3(name = "sparse_chunks_to_raw")]
pub fn py_sparse_chunks_to_raw(inputs: Vec<String>, output: &str) -> PyResult<()> {
    let paths: Vec<&Path> = inputs.iter().map(|s| Path::new(s.as_str())).collect();
    convert_sparse_chunks_to_raw(&paths, Path::new(output))
        .map_err(|e| PyIOError::new_err(e.to_string()))
}

/// Python-exposed: check if a file is an Android sparse image.
#[pyfunction]
#[pyo3(name = "is_sparse")]
pub fn py_is_sparse(path: &str) -> PyResult<bool> {
    Ok(check_sparse(Path::new(path)))
}
