#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

import brotli
from dumpyara.lib.libsdat2img import main as sdat2img
from pathlib import Path
from sebaubuntu_libs.liblogging import LOGI
from shutil import move
from subprocess import check_output

def get_raw_image(partition: str, path: Path):
	"""
	Convert a partition image to a raw image.

	This function handles brotli compression, sdat and sparse images.
	"""
	brotli_image = path / f"{partition}.new.dat.br"
	dat_image = path / f"{partition}.new.dat"
	transfer_list = path / f"{partition}.transfer.list"
	unsparsed_image = path / f"{partition}.unsparsed.img"
	raw_image = path / f"{partition}.img"

	if brotli_image.is_file():
		LOGI(f"Decompressing {brotli_image}")
		dat_image.write_bytes(brotli.decompress(brotli_image.read_bytes()))
		brotli_image.unlink()

	if dat_image.is_file() and transfer_list.is_file():
		LOGI(f"Converting {dat_image} to {raw_image}")
		sdat2img(transfer_list, dat_image, raw_image)
		dat_image.unlink()
		transfer_list.unlink()

	if raw_image.is_file():
		try:
			check_output(["simg2img", raw_image, unsparsed_image]) # TODO: Rewrite libsparse...
		except Exception:
			pass
		else:
			move(unsparsed_image, raw_image)

		return raw_image

	return None
