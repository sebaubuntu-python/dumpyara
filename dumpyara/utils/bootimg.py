#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from distutils.dir_util import copy_tree
from dumpyara.lib.libaik import AIKManager
from pathlib import Path

def extract_bootimg(file: Path, output_path: Path):
	output_path.mkdir(parents=True)

	aik_manager = AIKManager()
	image_info = aik_manager.extract(file)

	(output_path / "info.txt").write_text(str(image_info))

	if image_info.kernel:
		with image_info.kernel.open('rb') as f:
			(output_path / "kernel").write_bytes(f.read())

	if image_info.dt_image:
		with image_info.dt_image.open('rb') as f:
			(output_path / "dt.img").write_bytes(f.read())

	if image_info.dtb_image:
		with image_info.dtb_image.open('rb') as f:
			(output_path / "dtb.img").write_bytes(f.read())

	if image_info.dtbo_image:
		with image_info.dtbo_image.open('rb') as f:
			(output_path / "dtbo.img").write_bytes(f.read())

	if image_info.ramdisk:
		copy_tree(str(image_info.ramdisk), str(output_path / "ramdisk"), preserve_symlinks=True)

	aik_manager.cleanup()

	return output_path