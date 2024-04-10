# dumpyara

[![PyPI version](https://img.shields.io/pypi/v/dumpyara)](https://pypi.org/project/dumpyara/)
[![Codacy Badge](https://app.codacy.com/project/badge/Grade/85d2c39edbed4dc38f680db01f7b83af)](https://www.codacy.com/gh/sebaubuntu-python/dumpyara/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=sebaubuntu-python/dumpyara&amp;utm_campaign=Badge_Grade)

Requires Python 3.8 or greater

## Installation

```sh
pip3 install dumpyara
```

## Instructions

```sh
python3 -m dumpyara <path to OTA file>
```

## Supported formats

### Step 1 - Archives
-   All the ones supported by shutil's extract_archive
-   Samsung's `.tar.md5` archives
-   Nested archives

### Step 2 - What's inside the archive
-   A-only OTAs (Brotli and/or sdat compressed)
-   A/B OTAs
-   Dynamic partitions (super.img)
-   payload.bin
-   Raw images (e.g. Xiaomi fastboot packages)
-   Sparse images
-   LZ4 images

### Step 3 - Partition images
-   Android boot images
-   7z supported archives/images
-   EROFS images using erofs-utils

## Credits
-   AIK: osm0sis
-   [extract_android_ota_payload](https://github.com/erfanoabdi/extract_android_ota_payload): cyxx and erfanoabdi
-   sdat2img: xpirt

## License

```
#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#
```
