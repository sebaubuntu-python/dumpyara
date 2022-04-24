#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#
"""7z wrapper."""

from subprocess import check_output

def sevenz(command: str):
	return check_output(f"7z {command}", shell=True)
