# Dumpyara

[![Codacy Badge](https://app.codacy.com/project/badge/Grade/7b17f96d027e408ba3637d6215806e95)](https://www.codacy.com/gh/SebaUbuntu/dumpyara/dashboard?utm_source=github.com&amp;utm_medium=referral&amp;utm_content=SebaUbuntu/dumpyara&amp;utm_campaign=Badge_Grade)

## Installation

```
pip3 install dumpyara
```
The module is supported on Python 3.8 and above.

## How to use

```
$ python3 -m dumpyara -h
Dumpyara
Version 1.0.0

usage: python3 -m dumpyara [-h] [-o OUTPUT] [-v] file

positional arguments:
  file                  path to a device OTA

optional arguments:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
                        custom output folder
  -v, --verbose         enable debugging logging
```

## Supported formats

### Step 1 - Archives
- All the ones supported by shutil's extract_archive

### Step 2 - What's inside the archive
- A-only OTAs (Brotli and/or sdat compressed)
- A/B OTAs
- Dynamic partitions (super.img)
- payload.bin
- Raw images (e.g. Xiaomi fastboot packages)

### Step 3 - Partition images
- Raw images
- Sparsed images
- Boot images

## Credits
- AIK: osm0sis
- [extract_android_ota_payload](https://github.com/erfanoabdi/extract_android_ota_payload): cyxx and erfanoabdi
- lpunpack: unix3dgforce
- sdat2img: xpirt
