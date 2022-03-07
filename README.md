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

### Archives
- All the ones supported by shutil's extract_archive

### Images
- Raw images
- Brotli compressed images
- sdat images
- Sparsed images
- Boot images

## Credits
- AIK: osm0sis
- lpunpack: unix3dgforce
- sdat2img: xpirt
