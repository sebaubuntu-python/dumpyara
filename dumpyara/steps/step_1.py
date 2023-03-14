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
from shutil import move, unpack_archive

from dumpyara.utils.files import get_recursive_files_list

def step_1(archive_path: Path, extracted_archive_path: Path):
	"""
	Extract the archive into a folder.
	"""
	# Extract the archive
	unpack_archive(archive_path, extracted_archive_path)

	# Flatten the folder
	for file in get_recursive_files_list(extracted_archive_path):
		if file == extracted_archive_path / file.name:
			continue

		move(str(file), extracted_archive_path)
