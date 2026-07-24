#
# SPDX-FileCopyrightText: Dumpyara Project
# SPDX-License-Identifier: GPL-3.0-or-later
#

from typing import Callable, Dict
from liblp.partition_tools.lpunpack import lpunpack
from pathlib import Path
from re import Pattern, compile
from sebaubuntu_libs.liblogging import LOGI
from shutil import move, which
from subprocess import STDOUT, check_output

from dumpyara.lib.libpayload import extract_android_ota_payload

SIMG2IMG_EXECUTABLE = which("simg2img") or "simg2img"

try:
    import firmware_parsers
except ImportError:
    firmware_parsers = None


def extract_payload(image: Path, output_dir: Path):
    extract_android_ota_payload(image, output_dir)


def extract_super(image: Path, output_dir: Path):
    unsparsed_super = output_dir / "super.unsparsed.img"

    try:
        if firmware_parsers is not None:
            firmware_parsers.sparse_to_raw(str(image), str(unsparsed_super))
        else:
            check_output(  # nosec B603
                [SIMG2IMG_EXECUTABLE, image, unsparsed_super], stderr=STDOUT
            )
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
