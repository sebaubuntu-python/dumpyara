use pyo3::prelude::*;

pub mod detect;
pub mod mtk_sign;
pub mod nb0;
pub mod pac;
pub mod sparse;

#[pymodule]
fn firmware_parsers(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(detect::py_detect, m)?)?;
    m.add_function(wrap_pyfunction!(sparse::py_sparse_to_raw, m)?)?;
    m.add_function(wrap_pyfunction!(sparse::py_sparse_chunks_to_raw, m)?)?;
    m.add_function(wrap_pyfunction!(sparse::py_is_sparse, m)?)?;
    m.add_function(wrap_pyfunction!(nb0::py_extract, m)?)?;
    m.add_function(wrap_pyfunction!(pac::py_extract, m)?)?;
    m.add_function(wrap_pyfunction!(mtk_sign::py_extract, m)?)?;
    Ok(())
}
