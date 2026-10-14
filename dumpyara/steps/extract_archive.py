#
# SPDX-FileCopyrightText: Dumpyara Project
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""
Step 1.

This step will extract the archive into a folder.
"""

from io import BytesIO
from pathlib import Path, PurePosixPath
from re import Pattern, compile
from shutil import unpack_archive
from sebaubuntu_libs.liblogging import LOGD, LOGI
from typing import Callable, Dict
from zipfile import BadZipFile, ZipFile, is_zipfile

from dumpyara.utils.files import get_recursive_files_list
from dumpyara.utils.multipartitions import MULTIPARTITIONS
from dumpyara.utils.partitions import get_partition_names_with_ab
from dumpyara.utils.raw_image import (
    RAW_IMAGE_DATA_SUFFIXES,
    RAW_IMAGE_LZ4_SUFFIX,
    RAW_IMAGE_SUFFIXES,
    RAW_IMAGE_TRANSFER_LIST_SUFFIX,
)


MAX_NESTED_ZIP_DEPTH = 3
RAW_PARTITION_IMAGE_SUFFIXES = RAW_IMAGE_SUFFIXES + (RAW_IMAGE_LZ4_SUFFIX,)


def _contains_raw_partition_image(file_names: set[str]) -> bool:
    for partition in get_partition_names_with_ab():
        if any(f"{partition}{suffix}" in file_names for suffix in RAW_PARTITION_IMAGE_SUFFIXES):
            return True

        if f"{partition}{RAW_IMAGE_TRANSFER_LIST_SUFFIX}" in file_names and any(
            f"{partition}{suffix}" in file_names for suffix in RAW_IMAGE_DATA_SUFFIXES
        ):
            return True

    return False


def _is_nested_zip(file_name: str) -> bool:
    return PurePosixPath(file_name).name.endswith(".zip")


def _is_multipartition_image(file_name: str) -> bool:
    name = PurePosixPath(file_name).name
    return any(pattern.match(name) for pattern in MULTIPARTITIONS)


def _zip_contains_extractable_files(zip_file: ZipFile, nested_zip_depth: int) -> bool:
    file_names = zip_file.namelist()
    file_basenames = {PurePosixPath(file_name).name for file_name in file_names}

    if _contains_raw_partition_image(file_basenames):
        return True

    if any(_is_multipartition_image(file_name) for file_name in file_names):
        return True

    if nested_zip_depth >= MAX_NESTED_ZIP_DEPTH:
        return False

    for file_name in file_names:
        if not _is_nested_zip(file_name):
            continue

        try:
            with zip_file.open(file_name) as nested_file:
                with ZipFile(BytesIO(nested_file.read()), "r") as nested_zip:
                    if _zip_contains_extractable_files(
                        nested_zip,
                        nested_zip_depth + 1,
                    ):
                        return True
        except (BadZipFile, KeyError, RuntimeError) as e:
            LOGD(f"Failed to inspect nested zip member {file_name}: {e}")

    return False


def _has_extractable_nested_zip_contents(
    archive_path: Path,
    nested_zip_depth: int,
) -> bool:
    if not is_zipfile(archive_path):
        LOGD(f"Skipping nested zip scan for non-zip archive: {archive_path.name}")
        return False

    try:
        with ZipFile(archive_path, "r") as zip_file:
            return _zip_contains_extractable_files(zip_file, nested_zip_depth)
    except Exception as e:
        LOGD(f"Failed to inspect nested zip {archive_path.name}: {e}")
        return False


def extract_archive(
    archive_path: Path,
    extracted_archive_path: Path,
    is_nested: bool = False,
    nested_zip_depth: int = 0,
):
    """
    Extract the archive into a folder.
    """
    LOGD(f"Extracting archive: {archive_path.name}")

    # Extract the archive
    unpack_archive(archive_path, extracted_archive_path)
    if is_nested:
        LOGD("Archive is nested, unlinking")
        archive_path.unlink()

    # Flatten the folder
    for file in get_recursive_files_list(extracted_archive_path):
        if file == extracted_archive_path / file.name:
            continue

        file.rename(extracted_archive_path / file.name)

    # Check for nested archives
    extracted_archive_tempdir_files_list = list(
        get_recursive_files_list(extracted_archive_path, True)
    )
    for pattern, func in NESTED_ARCHIVES.items():
        matches = [
            file for file in extracted_archive_tempdir_files_list if pattern.match(str(file))
        ]

        if not matches:
            LOGI(f"Pattern {pattern.pattern} not found")
            continue

        for file in matches:
            nested_archive = extracted_archive_path / file

            LOGI(f"Found nested archive: {nested_archive.name}")

            if not nested_archive.is_file():
                LOGD(f"Nested archive {nested_archive.name} probably already handled, skipping")
                continue

            func(nested_archive, extracted_archive_path, True)

    nested_archive_patterns = tuple(NESTED_ARCHIVES.keys())
    for file in extracted_archive_tempdir_files_list:
        if any(pattern.match(str(file)) for pattern in nested_archive_patterns):
            continue

        if not _is_nested_zip(str(file)):
            continue

        nested_archive = extracted_archive_path / file
        LOGI(f"Found nested zip candidate: {nested_archive.name}")

        if not nested_archive.is_file():
            LOGD(f"Nested zip {nested_archive.name} probably already handled, skipping")
            continue

        next_nested_zip_depth = nested_zip_depth + 1
        if next_nested_zip_depth > MAX_NESTED_ZIP_DEPTH:
            LOGD(
                f"Skipping nested zip {nested_archive.name}: "
                f"max depth {MAX_NESTED_ZIP_DEPTH} reached"
            )
            continue

        if not _has_extractable_nested_zip_contents(
            nested_archive,
            next_nested_zip_depth,
        ):
            LOGD(f"Skipping nested zip {nested_archive.name}: no extractable files")
            continue

        extract_archive(
            nested_archive,
            extracted_archive_path,
            True,
            next_nested_zip_depth,
        )

    LOGD(f"Extracted archive: {archive_path.name}")


NESTED_ARCHIVES: Dict[Pattern[str], Callable[[Path, Path, bool], None]] = {
    compile(key): value
    for key, value in {
        ".*\\.tar\\.md5": extract_archive,
    }.items()
}
