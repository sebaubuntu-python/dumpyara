#
# Copyright (C) 2024 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

import shutil
from dumpyara.lib.libsevenz import sevenz_ext

def setup_shutil_formats():
	shutil.register_unpack_format('7z', ['.7z', '.bin', ], sevenz_ext)
