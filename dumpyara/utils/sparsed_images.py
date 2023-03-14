#
# Copyright (C) 2023 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from pathlib import Path
from sebaubuntu_libs.liblogging import LOGI
from subprocess import STDOUT, check_output

from dumpyara.utils.partitions import get_partition_names_with_alias

def prepare_sparsed_images(files_path: Path):
	"""
	Prepare sparse images for conversion.

	This function handles:
	- sparsechunk images
	"""
	for partition in get_partition_names_with_alias():
		output_image = files_path / f"{partition}.img"
		if output_image.is_file():
			continue

		# sparsechunk
		sparsechunk_image_base = f"{partition}.img_sparsechunk."
		sparsechunk_image_files = sorted(
			files_path.glob(f"{sparsechunk_image_base}*"),
			key=lambda x: int(x.name.split(".")[-1]),
		)
		if sparsechunk_image_files:
			LOGI(f"Preparing sparsechunk images for {partition}")
			LOGI(f"Converting {sparsechunk_image_files[0]} to {output_image.name}")
			check_output(["simg2img", *sparsechunk_image_files, output_image], stderr=STDOUT)
			for sparsechunk_image_file in sparsechunk_image_files:
				sparsechunk_image_file.unlink()
