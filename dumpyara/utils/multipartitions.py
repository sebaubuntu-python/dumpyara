#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from typing import Callable, Dict
from liblp.partition_tools.lpunpack import lpunpack
from pathlib import Path
from re import Pattern, compile
from sebaubuntu_libs.liblogging import LOGI
from shutil import move
from subprocess import STDOUT, check_output

from dumpyara.lib.libpayload import extract_android_ota_payload

def extract_payload(image: Path, output_dir: Path):
	extract_android_ota_payload(image, output_dir)

def extract_super(image: Path, output_dir: Path):
	unsparsed_super = output_dir / "super.unsparsed.img"

	try:
		check_output(["simg2img", image, unsparsed_super], stderr=STDOUT) # TODO: Rewrite libsparse...
	except Exception:
		LOGI(f"Failed to unsparse {image.name}")
	else:
		move(unsparsed_super, image)

	if unsparsed_super.is_file():
		unsparsed_super.unlink()

	lpunpack(image, output_dir)

MULTIPARTITIONS: Dict[Pattern[str], Callable[[Path, Path], None]] = {
	compile(key): value
	for key, value in {
		"payload.bin": extract_payload,
		"super(?!.*(_empty)).*\\.img": extract_super,
	}.items()
}
