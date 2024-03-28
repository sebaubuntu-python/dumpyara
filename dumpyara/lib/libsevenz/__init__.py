#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#
"""7z wrapper."""

from pathlib import Path
from subprocess import STDOUT, check_output

def sevenz(command: str):
	return check_output(f"7z {command}", shell=True, stderr=STDOUT)

def sevenz_ext(filename: str, work_dir: Path):
	sevenz(f'x {filename} -y -o"{work_dir}"/')
