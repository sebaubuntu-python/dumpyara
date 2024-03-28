#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#
"""7zip wrapper."""

from subprocess import STDOUT, check_output

def sevenzip(command: str):
	return check_output(f"7z {command}", shell=True, stderr=STDOUT)

def unpack_sevenzip(filename: str, work_dir: str):
	sevenzip(f'x {filename} -y -o"{work_dir}"/')
