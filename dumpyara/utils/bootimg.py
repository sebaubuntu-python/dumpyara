#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from pathlib import Path
from sebaubuntu_libs.libcompat.distutils.dir_util import copy_tree
from sebaubuntu_libs.libaik import AIKManager

def extract_bootimg(file: Path, output_path: Path):
	aik_manager = AIKManager()

	image_info = aik_manager.unpackimg(file, ignore_ramdisk_errors=True)

	output_path.mkdir(parents=True)

	(output_path / "info.txt").write_text(str(image_info))

	if image_info.kernel:
		(output_path / "kernel").write_bytes(image_info.kernel.read_bytes())

	if image_info.dt:
		(output_path / "dt.img").write_bytes(image_info.dt.read_bytes())

	if image_info.dtb:
		(output_path / "dtb.img").write_bytes(image_info.dtb.read_bytes())

	if image_info.dtbo:
		(output_path / "dtbo.img").write_bytes(image_info.dtbo.read_bytes())

	if image_info.ramdisk:
		copy_tree(str(image_info.ramdisk), str(output_path / "ramdisk"), preserve_symlinks=True)

	aik_manager.cleanup()

	return output_path
