#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from pathlib import Path
from sebaubuntu_libs.liblogging import LOGI
from sebaubuntu_libs.libstring import removesuffix
from shutil import move
from typing import List

from dumpyara.utils.raw_image import get_raw_image

(
	FILESYSTEM,
	BOOTIMAGE,
	RAW,
	LOGICAL,
) = range(4)

# partition: type
# Please document partition where possible
PARTITIONS = {
	# Bootloader/raw images
	## AOSP
	"boot": BOOTIMAGE,
	"boot-debug": BOOTIMAGE,
	"dtbo": RAW,
	"init_boot": BOOTIMAGE,
	"recovery": BOOTIMAGE,
	"vendor_boot": BOOTIMAGE,
	"vendor_boot-debug": BOOTIMAGE,
	"vendor_kernel_boot": BOOTIMAGE,

	## SoC vendor/OEM/ODM
	"exaid": BOOTIMAGE,
	"rescue": BOOTIMAGE,
	"tz": RAW,

	# Logical partitions
	## AOSP
	"super": LOGICAL,

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
	"mi_ext": FILESYSTEM,
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

def get_partition_name(partition_name: str):
	"""Get the unaliased partition name."""
	return ALTERNATIVE_PARTITION_NAMES.get(partition_name, partition_name)

def get_partition_names():
	"""Get a list of partition names."""
	return list(PARTITIONS)

def get_partition_names_with_alias():
	"""Get a list of partition names with alias."""
	return get_partition_names() + list(ALTERNATIVE_PARTITION_NAMES)

def get_partition_names_with_ab():
	"""Get a list of partition names with A/B variants.

	This is used during step 2 to also extract the A/B partitions."""
	partitions: List[str] = []

	for partition in get_partition_names_with_alias():
		partitions.append(partition)
		partitions.append(f"{partition}_a")
		partitions.append(f"{partition}_b")

	return partitions

def prepare_raw_images(files_path: Path, raw_images_path: Path):
	"""Prepare raw images for 7z extraction."""
	for partition_name in get_partition_names_with_ab():
		partition_output = raw_images_path / f"{partition_name}.img"

		get_raw_image(partition_name, files_path, partition_output)

def fix_aliases(images_path: Path):
	"""Move aliased partitions to their generic name."""
	for alt_name, name in ALTERNATIVE_PARTITION_NAMES.items():
		alt_path = images_path / f"{alt_name}.img"
		partition_path = images_path / f"{name}.img"

		if not alt_path.exists():
			continue

		if partition_path.exists():
			LOGI(f"Ignoring {alt_name} ({name} already extracted)")
			alt_path.unlink()

		LOGI(f"Fixing alias {alt_name} -> {name}")
		move(alt_path, partition_path)

def get_filename_suffixes(file: Path):
	return "".join(file.suffixes)

def get_filename_without_extensions(file: Path):
	return removesuffix(str(file.name), get_filename_suffixes(file))

def correct_ab_filenames(images_path: Path):
	partitions = get_partition_names_with_alias()
	for file in images_path.iterdir():
		if not file.is_file():
			continue

		file_stem = get_filename_without_extensions(file)

		if not file_stem.endswith("_a") and not file_stem.endswith("_b"):
			continue

		suffix = file_stem[-2:]
		file_stem_unslotted = removesuffix(file_stem, suffix)

		if file_stem_unslotted not in partitions:
			continue

		LOGI(f"correct_ab_filenames: file: {file}, file_stem: {file_stem}")

		non_ab_partition_path = images_path / f"{file_stem_unslotted}{get_filename_suffixes(file)}"
		a_partition_path = images_path / f"{file_stem_unslotted}_a{get_filename_suffixes(file)}"
		b_partition_path = images_path / f"{file_stem_unslotted}_b{get_filename_suffixes(file)}"

		if non_ab_partition_path.is_file():
			LOGI(f"correct_ab_filenames: {non_ab_partition_path} already exists, skipping")
			file.unlink()
			continue

		if a_partition_path.is_file():
			LOGI(f"correct_ab_filenames: {a_partition_path} -> {non_ab_partition_path}")
			move(a_partition_path, non_ab_partition_path)
		elif b_partition_path.is_file():
			LOGI(f"correct_ab_filenames: {b_partition_path} -> {non_ab_partition_path}")
			move(b_partition_path, non_ab_partition_path)
