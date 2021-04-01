#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from dumpyara.lib.liblogging import LOGE, LOGI
from dumpyara.lib.libsevenz import sevenz
from dumpyara.utils.raw_image import get_raw_image
from pathlib import Path
from shutil import copyfile
from subprocess import CalledProcessError

# partition: is_raw
PARTITIONS = {
	"boot": True,
	"dtbo": True,
	"cust": False,
	"factory": False,
	"india": True,
	"my_preload": True,
	"my_odm": True,
	"my_stock": True,
	"my_operator": True,
	"my_country": True,
	"my_product": True,
	"my_company": True,
	"my_engineering": True,
	"my_heytap": True,
	"odm": False,
	"oem": False,
	"oppo_product": False,
	"opproduct": True,
	"preload_common": False,
	"product": False,
	"recovery": True,
	"reserve": True,
	"system": False,
	"system_ext": False,
	"system_other": False,
	"systemex": False,
	"vendor": False,
	"xrom": False,
	"modem": True,
	"tz": True,
}

# alternative name: generic name
ALTERNATIVE_PARTITION_NAMES = {
	"boot-verified": "boot",
	"dtbo-verified": "dtbo",
	"NON-HLOS": "modem",
}

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

	if PARTITIONS[new_partition_name]:
		copyfile(file, output_path / f"{new_partition_name}.img", follow_symlinks=True)
	else:
		# Make sure we have a raw image
		raw_image = get_raw_image(partition_name, file.parent)

		# TODO: EROFS
		try:
			sevenz(f'x {raw_image} -y -o"{output_path / new_partition_name}"/')
		except CalledProcessError as e:
			LOGE(f"Error extracting {file.stem}")
			LOGE(f"{e.output}")
			raise e
