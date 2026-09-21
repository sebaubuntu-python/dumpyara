#
# SPDX-FileCopyrightText: Dumpyara Project
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""Run with: python3 tests/test_libext4.py /path/to/ext4.img /path/to/other.img"""

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dumpyara.lib.libext4 import extract_ext4, is_ext4  # noqa: E402


def main(ext4_image: Path, non_ext4_image: Path):
    assert is_ext4(ext4_image), f"{ext4_image} should be detected as ext4"
    assert not is_ext4(non_ext4_image), f"{non_ext4_image} should not be detected as ext4"

    with TemporaryDirectory() as tmp:
        extract_ext4(ext4_image, Path(tmp) / "out")
        links = [p for p in (Path(tmp) / "out").rglob("*") if p.is_symlink()]
        assert links, "no symlinks survived extraction"

    # debugfs exits 0 on a non-ext4 image; the wrapper must still raise
    with TemporaryDirectory() as tmp:
        try:
            extract_ext4(non_ext4_image, Path(tmp) / "out")
        except RuntimeError:
            pass
        else:
            raise AssertionError("silent failure on non-ext4 image")

    print("ok")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
