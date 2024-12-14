#
# Copyright (C) 2024 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#
"""fsck.erofs wrapper."""

from pathlib import Path
from subprocess import STDOUT, check_output

def extract_erofs(image: Path, output_dir: Path):
	return check_output(
		["fsck.erofs", f"--extract={output_dir}", f"{image}"],
		stderr=STDOUT
	)
