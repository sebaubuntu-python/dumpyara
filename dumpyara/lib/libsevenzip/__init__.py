#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#
"""7zip wrapper."""

from sebaubuntu_libs.liblogging import LOGW
from shutil import which
from subprocess import STDOUT, check_output
from typing import List

SEVEN_ZIP_EXECUTABLE = "7zz"
P7ZIP_EXECUTABLE = "7z"

_cached_executable = None

def get_sevenzip_command():
	global _cached_executable

	if _cached_executable:
		return _cached_executable
	elif which(SEVEN_ZIP_EXECUTABLE):
		_cached_executable = SEVEN_ZIP_EXECUTABLE
		return SEVEN_ZIP_EXECUTABLE
	elif which(P7ZIP_EXECUTABLE):
		LOGW("Using legacy p7zip, some features may not work")
		_cached_executable = P7ZIP_EXECUTABLE
		return P7ZIP_EXECUTABLE
	else:
		raise RuntimeError("You need 7-zip or p7zip installed to use this feature")

def sevenzip(commands: List[str]):
	return check_output(
		[get_sevenzip_command(), *commands],
		stderr=STDOUT
	)

def unpack_sevenzip(filename: str, work_dir: str):
	sevenzip_command = get_sevenzip_command()

	args = ["x", filename, "-y", f"-o{work_dir}/"]
	if sevenzip_command == SEVEN_ZIP_EXECUTABLE:
		# Enable dangerous symlinks extractions
		args.append("-snld")

	sevenzip(args)
