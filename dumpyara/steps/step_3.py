#
# Copyright (C) 2023 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#
"""
Step 3.

This step will extract the raw images.
"""

from pathlib import Path
from sebaubuntu_libs.libexception import format_exception
from sebaubuntu_libs.liblogging import LOGE, LOGI
from shutil import copyfile
from subprocess import CalledProcessError

from dumpyara.lib.libsevenz import sevenz
from dumpyara.utils.bootimg import extract_bootimg
from dumpyara.utils.partitions import (
	BOOTIMAGE, FILESYSTEM, RAW,
    PARTITIONS,
	get_partition_names,
)

def step_3(raw_images_path: Path, output_path: Path):
	"""
	Extract the raw images.
	"""
	# At this point aliases shouldn't be used anymore
	for partition in get_partition_names():
		partition_type = PARTITIONS[partition]

		image_path = raw_images_path / f"{partition}.img"
		if not image_path.exists():
			continue

		LOGI(f"Extracting {partition}")

		if partition_type == BOOTIMAGE:
			try:
				extract_bootimg(image_path, output_path / partition)
			except Exception as e:
				LOGE(f"Failed to extract {image_path.name}")
				LOGE(f"{format_exception(e)}")
		elif partition_type == FILESYSTEM:
			try:
				sevenz(f'x {image_path} -y -o"{output_path / partition}"/')
			except CalledProcessError as e:
				LOGE(f"Error extracting {image_path.name}")
				LOGE(f"{e.output.decode('UTF-8', errors='ignore')}")

		if partition_type in (RAW, BOOTIMAGE):
			copyfile(image_path, output_path / f"{partition}.img", follow_symlinks=True)
