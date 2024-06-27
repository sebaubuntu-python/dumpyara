#
# Copyright (C) 2024 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from py7zr import unpack_7zarchive
import shutil

from dumpyara.lib.libsevenzip import unpack_sevenzip
from dumpyara.lib.libkdz import unpack_kdz, unpack_dz

def unpack_tar_md5(filename: str, work_dir: str):
	"""
	Unpack a tar.md5 file.
	"""
	# Extract the tar file
	shutil.unpack_archive(filename, work_dir, "tar")

def setup_shutil_formats():
	# 7z archive
	shutil.register_unpack_format('7z', ['.7z'], unpack_7zarchive)

	# tar.md5 archive
	shutil.register_unpack_format('tar.md5', ['.tar.md5'], unpack_tar_md5)

	# 7zip archive, please use this as last resort if no Python lib exists
	shutil.register_unpack_format(
		'7zip',
		[
			'.bin'
		],
		unpack_sevenzip
	)

	# kdz archive
	shutil.register_unpack_format('kdz', ['.kdz'], unpack_kdz)

	# dz archive
	shutil.register_unpack_format('dz', ['.dz'], unpack_dz)
