#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

import brotli
from dumpyara.lib.libsdat2img import main as sdat2img
from dumpyara.lib.libsparseimg import SparseImage
from pathlib import Path
from sebaubuntu_libs.liblogging import LOGI
from shutil import move

def get_raw_image(partition: str, path: Path):
	"""
	Convert a partition image to a raw image.

	This function handles brotli compression, sdat and sparse images.
	"""
	brotli_image = path / f"{partition}.new.dat.br"
	dat_image = path / f"{partition}.new.dat"
	transfer_list = path / f"{partition}.transfer.list"
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
		with raw_image.open("rb") as f:
			sparse_image = SparseImage(f)
			if sparse_image.check():
				LOGI(f"{raw_image.stem} is a sparse image, extracting...")
				unsparse_file = sparse_image.unsparse()
				move(unsparse_file, raw_image)

		return raw_image

	return None
