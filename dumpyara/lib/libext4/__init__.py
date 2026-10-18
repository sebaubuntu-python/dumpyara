#
# SPDX-FileCopyrightText: Dumpyara Project
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""debugfs wrapper."""

from pathlib import Path
from subprocess import STDOUT, check_output

EXT4_SUPERBLOCK_OFFSET = 0x438
EXT4_MAGIC = b"\x53\xef"

# debugfs emits these for every inode when not running as root,
# but the data and symlinks are still extracted correctly
BENIGN_MESSAGES = (
    "Operation not permitted while changing ownership",
    "Operation not permitted while changing mode",
)


def is_ext4(image: Path):
    with image.open("rb") as f:
        f.seek(EXT4_SUPERBLOCK_OFFSET)
        return f.read(len(EXT4_MAGIC)) == EXT4_MAGIC


def extract_ext4(image: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)

    output = check_output(
        ["debugfs", "-R", f"rdump / {output_dir}", f"{image}"], stderr=STDOUT, text=True
    )

    # debugfs exits 0 even when it can't open the image at all, so the output
    # is the only way to tell a failed extraction from a successful one
    errors = [
        line
        for line in output.splitlines()[1:]
        if line.strip() and not any(benign in line for benign in BENIGN_MESSAGES)
    ]
    if errors:
        raise RuntimeError(f"debugfs failed to extract {image.name}: {errors[0]}")

    return output
