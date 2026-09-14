#
# SPDX-FileCopyrightText: Dumpyara Project
# SPDX-License-Identifier: GPL-3.0-or-later
#

from tempfile import mkdtemp
from typing import Callable, Dict
from liblp.partition_tools.lpunpack import lpunpack
from pathlib import Path
from re import Pattern, compile
from sebaubuntu_libs.liblogging import LOGI
from shutil import move, rmtree, which
from subprocess import STDOUT, check_output, run

from dumpyara.lib.libpayload import extract_android_ota_payload

SIMG2IMG_EXECUTABLE = which("simg2img") or "simg2img"
OTADUMP_EXECUTABLE = which("otadump")

try:
    from otadump import extract as extract_payload_native
except ImportError:
    extract_payload_native = None

try:
    import firmware_parsers
except ImportError:
    firmware_parsers = None


def _extract_payload_otadump(image: Path, output_dir: Path, otadump_bin: str):
    # Stage into a sibling tempdir so a partial failure does not leave half-written
    # images in output_dir alongside the real payload.bin. Move results across on success.
    staging = Path(mkdtemp(prefix=".otadump-", dir=output_dir))
    try:
        run(  # nosec B603
            [otadump_bin, "--output-dir", str(staging), str(image)],
            check=True,
        )
        for img in staging.iterdir():
            move(str(img), str(output_dir / img.name))
    finally:
        rmtree(staging, ignore_errors=True)


def extract_payload(image: Path, output_dir: Path):
    if extract_payload_native is not None:
        LOGI(f"Extracting {image.name} with native otadump bindings")
        extract_payload_native(image, output_dir, overwrite=True)
    elif OTADUMP_EXECUTABLE:
        LOGI(f"Extracting {image.name} with otadump ({OTADUMP_EXECUTABLE})")
        _extract_payload_otadump(image, output_dir, OTADUMP_EXECUTABLE)
    else:
        LOGI(f"Extracting {image.name} with vendored Python payload parser")
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
