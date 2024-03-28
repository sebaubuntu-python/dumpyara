#
# Copyright (C) 2024 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from py7zr import unpack_7zarchive
import shutil

from dumpyara.lib.libsevenzip import unpack_sevenzip

def setup_shutil_formats():
	# 7z archive
	shutil.register_unpack_format('7z', ['.7z'], unpack_7zarchive)

	# 7zip archive, please use this as last resort if no Python lib exists
	shutil.register_unpack_format(
		'7zip',
		[
			'.bin'
		],
		unpack_sevenzip
	)
