#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from dumpyara.lib.libsevenz import sevenz
from dumpyara.utils.bootimg import extract_bootimg
from dumpyara.utils.raw_image import get_raw_image
from pathlib import Path
from sebaubuntu_libs.libexception import format_exception
from sebaubuntu_libs.liblogging import LOGE, LOGI
from sebaubuntu_libs.libstring import removesuffix
from shutil import copyfile, move
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
ALTERNATIVE_PARTITION_NAMES.update({
	f"{partition}_a": partition
	for partition in PARTITIONS.keys()
})
ALTERNATIVE_PARTITION_NAMES.update({
	f"{partition}_b": partition
	for partition in PARTITIONS.keys()
})

def get_partition_name(partition_name: str):
	"""Get the unaliased partition name."""
	return ALTERNATIVE_PARTITION_NAMES.get(partition_name, partition_name)

def get_partition_names():
	"""Get a list of partition names."""
	return list(PARTITIONS)

def get_partition_names_with_alias():
	"""Get a list of partition names with alias."""
	return get_partition_names() + list(ALTERNATIVE_PARTITION_NAMES)

def prepare_raw_images(files_path: Path, raw_images_path: Path):
	"""Prepare raw images for 7z extraction."""
	for real_partition_name in get_partition_names_with_alias():
		partition_name = get_partition_name(real_partition_name)
		partition_output = raw_images_path / f"{partition_name}.img"

		get_raw_image(real_partition_name, files_path, partition_output)

def extract_partitions(raw_images_path: Path, output_path: Path):
	"""Extract partition files from raw images."""
	# At this point aliases shouldn't be used anymore
	for partition in get_partition_names():
		partition_type = PARTITIONS[partition]

		image_path = raw_images_path / f"{partition}.img"
		if not image_path.exists():
			continue

		LOGI(f"Extracting {partition}")

		if partition_type == BOOTIMAGE:
			try:
				extract_bootimg(image_path, output_path / partition)
			except Exception as e:
				LOGE(f"Failed to extract {image_path.name}")
				LOGE(f"{format_exception(e)}")
		elif partition_type == FILESYSTEM:
			try:
				sevenz(f'x {image_path} -y -o"{output_path / partition}"/')
			except CalledProcessError as e:
				LOGE(f"Error extracting {image_path.name}")
				LOGE(f"{e.output.decode('UTF-8', errors='ignore')}")

		if partition_type in (RAW, BOOTIMAGE):
			copyfile(image_path, output_path / f"{partition}.img", follow_symlinks=True)

def get_filename_suffixes(file: Path):
	return "".join(file.suffixes)

def get_filename_without_extensions(file: Path):
	return removesuffix(str(file.name), get_filename_suffixes(file))

def correct_ab_filenames(images_path: Path):
	partitions = get_partition_names_with_alias()
	for file in images_path.iterdir():
		file_stem = get_filename_without_extensions(file)

		for suffix in ["_a", "_b"]:
			if not file_stem.endswith(suffix):
				continue

			file_stem_unslotted = removesuffix(file_stem, suffix)

			if file_stem_unslotted not in partitions:
				continue

			new_image_path = images_path / f"{file_stem_unslotted}{get_filename_suffixes(file)}"

			if new_image_path.is_file():
				file.unlink()
				continue

			move(file, new_image_path)

			break
