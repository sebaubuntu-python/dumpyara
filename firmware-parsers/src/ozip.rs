use aes::cipher::{BlockDecrypt, KeyInit};
use aes::Aes128;
use anyhow::{bail, Context, Result};
use cipher::generic_array::GenericArray;
use hex_literal::hex;
use pyo3::exceptions::PyIOError;
use pyo3::prelude::*;
use std::fs::File;
use std::io::{BufReader, BufWriter, Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};

const OZIP_MAGIC: &[u8; 12] = b"OPPOENCRYPT!";
const HEADER_SIZE: u64 = 0x1050;
const BLOCK_ENC: usize = 16;
const BLOCK_PLAIN: usize = 0x4000;

/// Known AES-128-ECB keys from ozipdecrypt.py (open-source).
const KNOWN_KEYS: &[[u8; 16]] = &[
    hex!("D6EECF0AE5ACD4E0E9FE522DE7CE381E"),
    hex!("D6ECCF0AE5ACD4E0E92E522DE7C1381E"),
    hex!("D6DCCF0AD5ACD4E0292E522DB7C1381E"),
    hex!("D7DCCE1AD4AFDCE2393E5161CBDC4321"),
    hex!("D7DBCE2AD4ADDCE1393E5521CBDC4321"),
    hex!("D7DBCE1AD4AFDCE1393E5121CBDC4321"),
    hex!("D4D2CD61D4AFDCE13B5E01221BD14D20"),
    hex!("261CC7131D7C1481294E532DB752381E"),
    hex!("1CA21E12271335AE33AB81B2A7B14622"),
    hex!("D4D2CE11D4AFDCE13B3E0121CBD14D20"),
    hex!("1C4C1EA3A12531AE491B21BB31613C11"),
    hex!("1C4C1EA3A12531AE4A1B21BB31C13C21"),
    hex!("1C4A11A3A12513AE441B23BB31513121"),
    hex!("1C4A11A3A12589AE441A23BB31517733"),
    hex!("1C4A11A3A22513AE541B53BB31513121"),
    hex!("2442CE821A4F352E33AE81B22BC1462E"),
    hex!("14C2CD6214CFDC2733AE81B22BC1462C"),
    hex!("1E38C1B72D522E29E0D4ACD50ACFDCD6"),
    hex!("12341EAAC4C123CE193556A1BBCC232D"),
    hex!("2143DCCB21513E39E1DCAFD41ACEDBD7"),
    hex!("2D23CCBBA1563519CE23C1C4AA1E3412"),
    hex!("172B3E14E46F3CE13E2B5121CBDC4321"),
    hex!("ACAA1E12A71431CE4A1B21BBA1C1C6A2"),
    hex!("ACAC1E13A72531AE4A1B22BB31C1CC22"),
    hex!("1C4411A3A12533AE441B21BB31613C11"),
    hex!("1C4416A8A42717AE441523B336513121"),
    hex!("55EEAA33112133AE441B23BB31513121"),
    hex!("ACAC1E13A12531AE4A1B21BB31C13C21"),
    hex!("ACAC1E13A72431AE4A1B22BBA1C1C6A2"),
    hex!("12CAC11211AAC3AEA2658690122C1E81"),
    hex!("1CA21E12271435AE331B81BBA7C14612"),
    hex!("D1DACF24351CE428A9CE32ED87323216"),
    hex!("A1CC75115CAECB890E4A563CA1AC67C8"),
    hex!("2132321EA2CA86621A11241ABA512722"),
    hex!("22A21E821743E5EE33AE81B227B1462E"),
];

/// Check if data starts with OPPOENCRYPT! magic.
pub fn probe(data: &[u8]) -> bool {
    data.len() >= 12 && &data[0..12] == OZIP_MAGIC
}

/// Try each known key and check if decrypted first block looks valid.
fn find_key(first_enc_block: &[u8; 16]) -> Option<[u8; 16]> {
    for &key in KNOWN_KEYS {
        let cipher = Aes128::new(GenericArray::from_slice(&key));
        let mut block = GenericArray::clone_from_slice(first_enc_block);
        cipher.decrypt_block(&mut block);
        // Check for zip PK magic, ANDROID!, or AVB0
        if block.starts_with(b"PK\x03\x04")
            || block.starts_with(b"ANDR")
            || block.starts_with(b"AVB0")
        {
            return Some(key);
        }
    }
    None
}

/// Decrypt a mode-1 ozip (direct encrypted payload) to a file.
fn decrypt_mode1(input: &Path, output: &Path) -> Result<()> {
    let mut reader = BufReader::new(File::open(input)?);

    // Skip header
    reader.seek(SeekFrom::Start(HEADER_SIZE))?;

    // Read first encrypted block to find the key
    let mut first_block = [0u8; BLOCK_ENC];
    reader.read_exact(&mut first_block)?;
    reader.seek(SeekFrom::Start(HEADER_SIZE))?;

    let key = find_key(&first_block).context("no matching OPPO decryption key found")?;
    let cipher = Aes128::new(GenericArray::from_slice(&key));

    let file_size = std::fs::metadata(input)?.len();
    let payload_size = file_size - HEADER_SIZE;

    let mut writer = BufWriter::new(File::create(output)?);
    let mut remaining = payload_size;

    while remaining > 0 {
        // Encrypted block (16 bytes)
        if remaining >= BLOCK_ENC as u64 {
            let mut enc_buf = [0u8; BLOCK_ENC];
            reader.read_exact(&mut enc_buf)?;
            let mut block = GenericArray::clone_from_slice(&enc_buf);
            cipher.decrypt_block(&mut block);
            writer.write_all(&block)?;
            remaining -= BLOCK_ENC as u64;
        } else {
            // Remaining bytes less than a block — copy as-is
            let mut tail = vec![0u8; remaining as usize];
            reader.read_exact(&mut tail)?;
            writer.write_all(&tail)?;
            break;
        }

        // Plaintext block (0x4000 bytes)
        if remaining > 0 {
            let plain_len = remaining.min(BLOCK_PLAIN as u64) as usize;
            let mut plain_buf = vec![0u8; plain_len];
            reader.read_exact(&mut plain_buf)?;
            writer.write_all(&plain_buf)?;
            remaining -= plain_len as u64;
        }
    }

    Ok(())
}

/// Strip .ozip extension and return a useful output name.
/// "boot.ozip" → "boot", "system.new.dat.br.ozip" → "system.new.dat.br"
fn strip_ozip_ext(name: &str) -> &str {
    name.strip_suffix(".ozip")
        .or_else(|| name.strip_suffix(".OZIP"))
        .unwrap_or(name)
}

/// Extract a mode-1 OPPOENCRYPT! file: decrypt, then unpack inner zip if applicable.
fn extract_mode1(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let stem = input
        .file_stem()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_else(|| "output".to_string());

    // Decrypt to a temporary file
    let decrypted_path = output_dir.join(format!("_ozip_tmp_{stem}.zip"));
    decrypt_mode1(input, &decrypted_path)?;

    // Check what we got
    let mut decrypted = File::open(&decrypted_path)?;
    let mut zip_magic = [0u8; 4];
    let _ = decrypted.read(&mut zip_magic);
    drop(decrypted);

    let mut extracted = Vec::new();

    if &zip_magic[0..2] == b"PK" {
        // Decrypted to a zip — extract and decrypt any inner .ozip members
        extracted = extract_zip_contents(&decrypted_path, output_dir)?;
        let _ = std::fs::remove_file(&decrypted_path);
    } else {
        // Raw decrypted payload — preserve the stem name as-is.
        // stem is the input name minus .ozip (e.g. "system.new.dat.br"),
        // so we must NOT append .img or we'll break downstream matching.
        let final_path = output_dir.join(&stem);
        std::fs::rename(&decrypted_path, &final_path)?;
        extracted.push(final_path);
    }

    Ok(extracted)
}

/// Extract a mode-2 zip-wrapped ozip: the outer file is a standard zip
/// containing .ozip entries that each carry the OPPOENCRYPT! magic.
fn extract_mode2(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    extract_zip_contents(input, output_dir)
}

/// Common helper: given a zip file, extract all entries. For any entry
/// whose content starts with OPPOENCRYPT!, decrypt it in-place.
/// Strips the .ozip extension from decrypted member names.
fn extract_zip_contents(zip_path: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let zip_file = File::open(zip_path)?;
    let mut archive = zip::ZipArchive::new(zip_file)?;

    // Use a temp directory for intermediate files so cleanup is automatic
    let work_dir = output_dir.join("_ozip_work");
    std::fs::create_dir_all(&work_dir)?;

    let result = extract_zip_contents_inner(&mut archive, &work_dir, output_dir);

    // Always clean up the work directory
    let _ = std::fs::remove_dir_all(&work_dir);

    result
}

fn extract_zip_contents_inner(
    archive: &mut zip::ZipArchive<File>,
    work_dir: &Path,
    output_dir: &Path,
) -> Result<Vec<PathBuf>> {
    let mut extracted = Vec::new();

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

        // Write entry to work dir (need to inspect magic)
        let tmp_path = work_dir.join(&base_name);
        {
            let mut out_file = File::create(&tmp_path)?;
            std::io::copy(&mut entry, &mut out_file)?;
        }

        // Check if it's an encrypted ozip
        let mut inner_magic = [0u8; 12];
        let is_ozip = if let Ok(mut f) = File::open(&tmp_path) {
            f.read_exact(&mut inner_magic).is_ok() && &inner_magic == OZIP_MAGIC
        } else {
            false
        };

        if is_ozip {
            // Decrypt it — use name without .ozip extension
            let final_name = strip_ozip_ext(&base_name);
            let final_path = output_dir.join(final_name);
            let decrypted_tmp = work_dir.join(format!("_dec_{base_name}"));

            // Propagate decryption failure — do not silently rename ciphertext
            // to the output name, as downstream would try to parse encrypted bytes.
            decrypt_mode1(&tmp_path, &decrypted_tmp)
                .with_context(|| format!("failed to decrypt inner ozip member: {base_name}"))?;
            std::fs::rename(&decrypted_tmp, &final_path)?;
            extracted.push(final_path);
        } else {
            // Not encrypted — move to final name
            let final_path = output_dir.join(&base_name);
            std::fs::rename(&tmp_path, &final_path)?;
            extracted.push(final_path);
        }
    }

    Ok(extracted)
}

pub fn extract(input: &Path, output_dir: &Path) -> Result<Vec<PathBuf>> {
    let mut f = File::open(input)?;
    let mut magic = [0u8; 12];
    f.read_exact(&mut magic)?;
    drop(f);

    // Mode 2: outer file is a standard zip containing .ozip entries
    if &magic[0..2] == b"PK" {
        return extract_mode2(input, output_dir);
    }

    // Mode 1: direct OPPOENCRYPT! payload
    if &magic == OZIP_MAGIC {
        return extract_mode1(input, output_dir);
    }

    bail!("not an OPPO ozip file (magic: {:?})", &magic[0..4]);
}

/// Check if a zip archive contains .ozip entries (mode 2: zip-wrapped ozip).
pub fn probe_zip(archive: &zip::ZipArchive<File>) -> bool {
    (0..archive.len()).any(|i| {
        archive
            .name_for_index(i)
            .map(|n| n.to_lowercase().ends_with(".ozip"))
            .unwrap_or(false)
    })
}

#[pyfunction]
#[pyo3(name = "ozip")]
pub fn py_extract(input: &str, output_dir: &str) -> PyResult<Vec<String>> {
    let results = extract(Path::new(input), Path::new(output_dir))
        .map_err(|e| PyIOError::new_err(e.to_string()))?;
    Ok(results
        .into_iter()
        .map(|p| p.to_string_lossy().into_owned())
        .collect())
}
