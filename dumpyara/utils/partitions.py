#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from dumpyara.lib.libsevenz import sevenz
from dumpyara.utils.bootimg import extract_bootimg
from dumpyara.utils.raw_image import get_raw_image
from pathlib import Path
from sebaubuntu_libs.liblogging import LOGE, LOGI
from shutil import copyfile
from subprocess import CalledProcessError

(
	FILESYSTEM,
	BOOTIMAGE,
	RAW,
) = range(3)

# partition: type
# Please document partition where possible
PARTITIONS = {
	# Bootloader/raw images
	## AOSP
	"boot": BOOTIMAGE,
	"dtbo": RAW,
	"recovery": BOOTIMAGE,
	"vendor_boot": BOOTIMAGE,

	## SoC vendor/OEM/ODM
	"exaid": BOOTIMAGE,
	"tz": RAW,

	# Partitions with a standard filesystem
	## AOSP
	"odm": FILESYSTEM,
	"odm_dlkm": FILESYSTEM,
	"oem": FILESYSTEM,
	"product": FILESYSTEM,
	"system": FILESYSTEM,
	"system_dlkm": FILESYSTEM,
	"system_ext": FILESYSTEM,
	"system_other": FILESYSTEM,
	"vendor": FILESYSTEM,
	"vendor_dlkm": FILESYSTEM,

	## SoC vendor/OEM/ODM
	"cust": FILESYSTEM,
	"factory": FILESYSTEM,
	"india": FILESYSTEM,
	"modem": FILESYSTEM,
	"my_bigball": FILESYSTEM,
	"my_carrier": FILESYSTEM,
	"my_company": FILESYSTEM,
	"my_country": FILESYSTEM,
	"my_custom": FILESYSTEM,
	"my_engineering": FILESYSTEM,
	"my_heytap": FILESYSTEM,
	"my_manifest": FILESYSTEM,
	"my_odm": FILESYSTEM,
	"my_operator": FILESYSTEM,
	"my_preload": FILESYSTEM,
	"my_product": FILESYSTEM,
	"my_region": FILESYSTEM,
	"my_stock": FILESYSTEM,
	"my_version": FILESYSTEM,
	"odm_ext": FILESYSTEM,
	"oppo_product": FILESYSTEM,
	"opproduct": FILESYSTEM,
	"preload_common": FILESYSTEM,
	"reserve": FILESYSTEM,
	"special_preload": FILESYSTEM,
	"systemex": FILESYSTEM,
	"xrom": FILESYSTEM,
}

# alternative name: generic name
ALTERNATIVE_PARTITION_NAMES = {
	"boot-verified": "boot",
	"dtbo-verified": "dtbo",
	"NON-HLOS": "modem",
}

def get_partition_name(file: Path):
	"""
	Get the partition name from the file name.

	Returns a tuple of (partition name, output name).
	"""
	real_partition_name = str(file.name).removesuffix("".join(file.suffixes))

	for partition in list(PARTITIONS) + list(ALTERNATIVE_PARTITION_NAMES):
		if not real_partition_name in [partition, f"{partition}_a", f"{partition}_b"]:
			continue

		return ALTERNATIVE_PARTITION_NAMES.get(partition, partition), real_partition_name

	return None, None

def can_be_partition(file: Path):
	"""Check if the file can be a partition."""
	return get_partition_name(file) is not None

def extract_partition(file: Path, output_path: Path):
	"""
	Extract files from partition image.

	If the partition is raw, the file will simply be copied to the output folder,
	else extracted using 7z (unsparsed if needed).
	"""
	partition_name, output_name = get_partition_name(file)
	if not partition_name:
		LOGI(f"Skipping {file.stem}")
		return

	if PARTITIONS[partition_name] == FILESYSTEM:
		# Make sure we have a raw image
		raw_image = get_raw_image(output_name, file.parent)

		# TODO: EROFS
		try:
			sevenz(f'x {raw_image} -y -o"{output_path / output_name}"/')
		except CalledProcessError as e:
			LOGE(f"Error extracting {file.stem}")
			LOGE(f"{e.output.decode('UTF-8', errors='ignore')}")
	elif PARTITIONS[partition_name] == BOOTIMAGE:
		try:
			extract_bootimg(file, output_path / output_name)
		except Exception as e:
			LOGE(f"Failed to extract {file.name}, invalid boot image")

	if PARTITIONS[partition_name] in (RAW, BOOTIMAGE):
		copyfile(file, output_path / f"{output_name}.img", follow_symlinks=True)
