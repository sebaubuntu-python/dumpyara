#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from argparse import ArgumentParser
from dumpyara import __version__ as version, current_path
from dumpyara.dumpyara import Dumpyara
from dumpyara.utils.logging import setup_logging
from pathlib import Path

def main():
	print(f"Dumpyara\n"
		  f"Version {version}\n")

	parser = ArgumentParser(prog='python3 -m dumpyara')

	# Main arguments
	parser.add_argument("file", type=Path,
						help="path to a device OTA")
	parser.add_argument("-o", "--output", type=Path, default=current_path / "working",
						help="custom output folder")

	# Optional arguments
	parser.add_argument("-v", "--verbose", action='store_true',
						help="enable debugging logging")

	args = parser.parse_args()

	setup_logging(args.verbose)

	dumpyara = Dumpyara(args.file, args.output)

	print(f"\nDone! You can find the dump in {str(dumpyara.path)}")
