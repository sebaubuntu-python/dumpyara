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
PARTITIONS = {
	"boot": BOOTIMAGE,
	"dtbo": RAW,
	"cust": FILESYSTEM,
	"exaid": BOOTIMAGE,
	"factory": FILESYSTEM,
	"india": RAW,
	"my_preload": RAW,
	"my_odm": RAW,
	"my_stock": RAW,
	"my_operator": RAW,
	"my_country": RAW,
	"my_product": RAW,
	"my_company": RAW,
	"my_engineering": RAW,
	"my_heytap": RAW,
	"odm": FILESYSTEM,
	"odm_dlkm": FILESYSTEM,
	"oem": FILESYSTEM,
	"oppo_product": FILESYSTEM,
	"opproduct": RAW,
	"preload_common": FILESYSTEM,
	"product": FILESYSTEM,
	"recovery": BOOTIMAGE,
	"reserve": RAW,
	"system": FILESYSTEM,
	"system_ext": FILESYSTEM,
	"system_other": FILESYSTEM,
	"systemex": FILESYSTEM,
	"vendor": FILESYSTEM,
	"vendor_boot": BOOTIMAGE,
	"vendor_dlkm": FILESYSTEM,
	"xrom": FILESYSTEM,
	"modem": RAW,
	"tz": RAW,
}

# alternative name: generic name
ALTERNATIVE_PARTITION_NAMES = {
	"boot-verified": "boot",
	"dtbo-verified": "dtbo",
	"NON-HLOS": "modem",
}

# A/B partition, hoping _a is the right one...
ALTERNATIVE_PARTITION_NAMES.update({
	f"{alias}_a": partition
	for alias, partition in ALTERNATIVE_PARTITION_NAMES.items()
})
ALTERNATIVE_PARTITION_NAMES.update({
	f"{partition}_a": partition
	for partition in PARTITIONS
})

def get_partition_name(file: Path):
	for partition in list(PARTITIONS) + list(ALTERNATIVE_PARTITION_NAMES):
		possible_names = [
			partition,
			f"{partition}.bin",
			f"{partition}.ext4",
			f"{partition}.image",
			f"{partition}.img",
			f"{partition}.mbn",
			f"{partition}.new.dat",
			f"{partition}.new.dat.br",
			f"{partition}.raw",
			f"{partition}.raw.img",
		]
		if file.name in possible_names:
			return partition

	return None

def can_be_partition(file: Path):
	"""Check if the file can be a partition."""
	return get_partition_name(file) is not None

def extract_partition(file: Path, output_path: Path):
	"""
	Extract files from partition image.
	
	If the partition is raw, the file will simply be copied to the output folder,
	else extracted using 7z (unsparsed if needed).
	"""
	partition_name = get_partition_name(file)
	if not partition_name:
		LOGI(f"Skipping {file.stem}")
		return

	new_partition_name = ALTERNATIVE_PARTITION_NAMES.get(partition_name, partition_name)

	if PARTITIONS[new_partition_name] == FILESYSTEM:
		# Make sure we have a raw image
		raw_image = get_raw_image(partition_name, file.parent)

		# TODO: EROFS
		try:
			sevenz(f'x {raw_image} -y -o"{output_path / new_partition_name}"/')
		except CalledProcessError as e:
			LOGE(f"Error extracting {file.stem}")
			LOGE(f"{e.output}")
			raise e
	elif PARTITIONS[new_partition_name] == BOOTIMAGE:
		extract_bootimg(file, output_path / new_partition_name)

	if PARTITIONS[new_partition_name] in (RAW, BOOTIMAGE):
		copyfile(file, output_path / f"{new_partition_name}.img", follow_symlinks=True)
