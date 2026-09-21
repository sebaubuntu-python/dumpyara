# dumpyara

[![PyPI version](https://img.shields.io/pypi/v/dumpyara)](https://pypi.org/project/dumpyara/)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/85d2c39edbed4dc38f680db01f7b83af)](https://app.codacy.com/gh/sebaubuntu-python/dumpyara/dashboard?utm_source=gh&utm_medium=referral&utm_content=&utm_campaign=Badge_grade)

Requires Python 3.9 or greater

## Requirements

Besides Python, the following tools must be available in `PATH`:

- [7-zip](https://www.7-zip.org/) (`7zz`) or p7zip (`7z`)
- [erofs-utils](https://github.com/erofs/erofs-utils) **1.8 or greater** (`fsck.erofs`)
- [e2fsprogs](https://e2fsprogs.sourceforge.net/) (`debugfs`)
- `simg2img`, from android-sdk-libsparse-utils or platform-utils, unless
  `firmware_parsers` is installed

erofs-utils older than 1.8 must not be used: `fsck.erofs --extract` silently
drops holes in chunk-based files, producing truncated output while still
exiting 0, so corrupt dumps are published without any error. This was fixed
upstream in [`b063ea3`](https://github.com/erofs/erofs-utils/commit/b063ea316aa9fde2e878d7cbc7892dd9820d3bf7),
first released in 1.8. Distro packages are often far older than that, so
check `fsck.erofs -V` rather than assuming.

## Installation

```sh
pip install dumpyara
```

## Instructions

```sh
python -m dumpyara <path to OTA file>
```

## Supported formats

### Step 1 - Archives

- All the ones supported by shutil's extract_archive
- Samsung's `.tar.md5` archives
- Nested archives
- LG's `.kdz` archives

### Step 2 - What's inside the archive

- A-only OTAs (Brotli and/or sdat compressed)
- A/B OTAs
- Dynamic partitions (super.img)
- payload.bin
- Raw images (e.g. Xiaomi fastboot packages)
- Sparse images
- LZ4 images

### Step 3 - Partition images

- Android boot images
- 7z supported archives/images
- EROFS images using erofs-utils (1.8 or greater)
- ext4 images using debugfs, which preserves symlinks that 7z rewrites

## Credits

- AIK: osm0sis
- [extract_android_ota_payload](https://github.com/erfanoabdi/extract_android_ota_payload): cyxx and erfanoabdi
- sdat2img: xpirt

## License

```
#
# SPDX-FileCopyrightText: Dumpyara Project
# SPDX-License-Identifier: GPL-3.0-or-later
#
```
