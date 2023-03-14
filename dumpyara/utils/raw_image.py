#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

import brotli
from dumpyara.lib.libsdat2img import main as sdat2img
from pathlib import Path
from sebaubuntu_libs.liblogging import LOGI
from shutil import copyfile, move
from subprocess import STDOUT, check_output

def get_raw_image(partition: str, files_path: Path, output_image_path: Path):
	"""
	Convert a partition image to a raw image.

	This function handles brotli compression, sdat and sparse images.
	"""
	brotli_image = files_path / f"{partition}.new.dat.br"
	dat_image = files_path / f"{partition}.new.dat"
	transfer_list = files_path / f"{partition}.transfer.list"
	raw_image = files_path / f"{partition}.img"
	unsparsed_image = files_path / f"{partition}.unsparsed.img"
	possible_image_names = [
		f"{partition}",
		f"{partition}.bin",
		f"{partition}.ext4",
		f"{partition}.image",
		f"{partition}.img",
		f"{partition}.mbn",
		f"{partition}.raw",
		f"{partition}.raw.img",
	]

	if brotli_image.is_file():
		LOGI(f"Decompressing {brotli_image.name}")
		dat_image.write_bytes(brotli.decompress(brotli_image.read_bytes()))

	if dat_image.is_file() and transfer_list.is_file():
		LOGI(f"Converting {dat_image.name} to {raw_image.name}")
		sdat2img(transfer_list, dat_image, raw_image)

	for image_name in possible_image_names:
		image_path = files_path / image_name
		if not image_path.is_file():
			continue

		try:
			check_output(["simg2img", image_path, unsparsed_image], stderr=STDOUT) # TODO: Rewrite libsparse...
		except Exception:
			pass
		else:
			move(unsparsed_image, image_path)

		if unsparsed_image.is_file():
			unsparsed_image.unlink()

		LOGI(f"Copying {image_path.name}")
		copyfile(image_path, output_image_path, follow_symlinks=True)
		return True

	return False
