#
# Copyright (C) 2023 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
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

def extract_archive(archive_path: Path, extracted_archive_path: Path, is_nested: bool = False):
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
	extracted_archive_tempdir_files_list = list(get_recursive_files_list(extracted_archive_path, True))
	for pattern, func in NESTED_ARCHIVES.items():
		matches = [
			file for file in extracted_archive_tempdir_files_list
			if pattern.match(str(file))
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
