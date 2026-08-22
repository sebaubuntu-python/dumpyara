#
# SPDX-FileCopyrightText: Dumpyara Project
# SPDX-License-Identifier: GPL-3.0-or-later
#

import brotli
from dumpyara.lib.libsdat2img import main as sdat2img
import io
from lz4.frame import LZ4FrameFile
from pathlib import Path
from sebaubuntu_libs.liblogging import LOGD, LOGI
from shutil import copyfile, move
from subprocess import STDOUT, check_output


RAW_IMAGE_SUFFIXES = (
    "",
    ".bin",
    ".ext4",
    ".image",
    ".img",
    ".img.ext4",
    ".mbn",
    ".raw",
    ".raw.img",
)
RAW_IMAGE_LZ4_SUFFIX = ".img.lz4"
RAW_IMAGE_DAT_SUFFIX = ".new.dat"
RAW_IMAGE_BROTLI_SUFFIX = ".new.dat.br"
RAW_IMAGE_DATA_SUFFIXES = (
    RAW_IMAGE_DAT_SUFFIX,
    RAW_IMAGE_BROTLI_SUFFIX,
)
RAW_IMAGE_TRANSFER_LIST_SUFFIX = ".transfer.list"


def get_raw_image(partition: str, files_path: Path, output_image_path: Path):
    """
    Convert a partition image to a raw image.

    This function handles brotli compression, sdat and sparse images.
    """
    brotli_image = files_path / f"{partition}{RAW_IMAGE_BROTLI_SUFFIX}"
    dat_image = files_path / f"{partition}{RAW_IMAGE_DAT_SUFFIX}"
    transfer_list = files_path / f"{partition}{RAW_IMAGE_TRANSFER_LIST_SUFFIX}"
    lz4_image = files_path / f"{partition}{RAW_IMAGE_LZ4_SUFFIX}"
    raw_image = files_path / f"{partition}.img"
    unsparsed_image = files_path / f"{partition}.unsparsed.img"
    possible_image_names = [f"{partition}{suffix}" for suffix in RAW_IMAGE_SUFFIXES]

    if brotli_image.is_file():
        LOGI(f"Decompressing {brotli_image.name} as brotli image")
        dat_image.write_bytes(brotli.decompress(brotli_image.read_bytes()))

    if dat_image.is_file() and transfer_list.is_file():
        LOGI(f"Converting {dat_image.name} to {raw_image.name}")
        sdat2img(transfer_list, dat_image, raw_image)

    if lz4_image.is_file():
        LOGI(f"Decompressing {lz4_image.name} as LZ4 image")
        with LZ4FrameFile(lz4_image, mode="rb") as lz4_frame_file:
            with io.open(raw_image, "wb") as raw_image:
                raw_image.write(lz4_frame_file.read())

        lz4_image.unlink()

    for image_name in possible_image_names:
        image_path = files_path / image_name
        if not image_path.is_file():
            continue

        try:
            check_output(
                ["simg2img", image_path, unsparsed_image], stderr=STDOUT
            )  # TODO: Rewrite libsparse...
        except Exception:
            LOGD(f"Failed to unsparse {image_path.name}, should be a raw image")
            pass
        else:
            move(unsparsed_image, image_path)

        if unsparsed_image.is_file():
            unsparsed_image.unlink()

        LOGI(f"Copying {image_path.name}")
        copyfile(image_path, output_image_path, follow_symlinks=True)
        return True

    LOGD(f"Partition {partition} not found")

    return False
