#
# SPDX-FileCopyrightText: Dumpyara Project
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""
Step 1.

This step will extract the archive into a folder.
"""

from pathlib import Path
from re import Pattern, compile
from shutil import unpack_archive
from sebaubuntu_libs.liblogging import LOGD, LOGI
from typing import Callable, Dict

from dumpyara.utils.files import get_recursive_files_list

try:
    import firmware_parsers

    _HAS_FIRMWARE_PARSERS = True
except ImportError:
    _HAS_FIRMWARE_PARSERS = False


def extract_archive(archive_path: Path, extracted_archive_path: Path, is_nested: bool = False):
    """
    Extract the archive into a folder.
    """
    LOGD(f"Extracting archive: {archive_path.name}")

    # Try firmware_parsers detection first
    if _HAS_FIRMWARE_PARSERS:
        try:
            firmware_format = firmware_parsers.detect(str(archive_path))
            if firmware_format != "unknown":
                extractor = getattr(firmware_parsers, firmware_format, None)
                if extractor is not None:
                    LOGI(f"Detected firmware format: {firmware_format}")
                    extractor(str(archive_path), str(extracted_archive_path))
                    if is_nested:
                        archive_path.unlink()
                    return
        except Exception as error:
            LOGI(
                f"firmware_parsers failed ({error}), falling back to generic extraction"
            )

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

    # Re-detect firmware formats in extracted files
    if _HAS_FIRMWARE_PARSERS:
        for file in list(get_recursive_files_list(extracted_archive_path)):
            try:
                firmware_format = firmware_parsers.detect(str(file))
                if firmware_format != "unknown":
                    extractor = getattr(firmware_parsers, firmware_format, None)
                    if extractor is not None:
                        LOGI(
                            f"Detected nested firmware format: {firmware_format} "
                            f"in {file.name}"
                        )
                        extractor(str(file), str(extracted_archive_path))
                        file.unlink()
            except Exception as error:
                LOGD(f"firmware_parsers failed on {file.name}: {error}")

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

    LOGD(f"Extracted archive: {archive_path.name}")


NESTED_ARCHIVES: Dict[Pattern[str], Callable[[Path, Path, bool], None]] = {
    compile(key): value
    for key, value in {
        ".*\\.tar\\.md5": extract_archive,
    }.items()
}
