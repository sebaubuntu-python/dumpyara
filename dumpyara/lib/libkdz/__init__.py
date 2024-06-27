#
# Copyright (C) 2024 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#
"""kdz wrapper."""

import os
from pathlib import Path
from dumpyara.lib.libkdz.unkdz import KDZFileTools
from dumpyara.lib.libkdz.undz import DZFileTools, UNDZFile

def unpack_kdz(filename: str, work_dir: str):
	kdztools = KDZFileTools()
	kdztools.outdir = work_dir
	kdztools.kdzfile = filename
	kdztools.openFile(kdztools.kdzfile)
	kdztools.partList = kdztools.getPartitions()
	kdztools.cmdExtractAll()
	# Now we should have .dz file
	dz_file = list(Path(work_dir).glob("*.dz"))
	if dz_file:
		# Just take the first found file
		unpack_dz(dz_file[0].absolute(), work_dir)

def unpack_dz(filename: str, work_dir: str):
	dztools = DZFileTools()
	dztools.dz_file = UNDZFile(filename)
	os.chdir(work_dir)
	dztools.cmdExtractSlice([])