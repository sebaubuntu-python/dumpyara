#
# Copyright (C) 2023 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#
"""
Step 2.

This step will convert the archive files to raw images ready to be extracted.
"""

import fnmatch
from pathlib import Path
from sebaubuntu_libs.liblogging import LOGI

from dumpyara.utils.files import get_recursive_files_list
from dumpyara.utils.multipartitions import MULTIPARTITIONS
from dumpyara.utils.partitions import (
    correct_ab_filenames,
	fix_aliases,
	prepare_raw_images,
)
from dumpyara.utils.sparsed_images import prepare_sparsed_images

def step_2(extracted_archive_path: Path, raw_images_path: Path):
	"""
	Convert the archive files to raw images ready to be extracted.
	"""
    # Check for sparsed images
	prepare_sparsed_images(extracted_archive_path)

	# Check for multipartitions
	extracted_archive_tempdir_files_list = list(get_recursive_files_list(extracted_archive_path, True, True))
	for pattern, func in MULTIPARTITIONS.items():
		match = fnmatch.filter(extracted_archive_tempdir_files_list, pattern)
		if not match:
			LOGI(f"Pattern {pattern} not found")
			continue

		for file in match:
			multipart_image = extracted_archive_path / file
			LOGI(f"Found multipartition image: {multipart_image.name}")
			func(multipart_image, raw_images_path)

	# Check for partitions
	prepare_raw_images(extracted_archive_path, raw_images_path)

	# Fix slotted filenames if needed
	correct_ab_filenames(raw_images_path)

	# Fix aliases
	fix_aliases(raw_images_path)
