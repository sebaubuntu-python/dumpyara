#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from dumpyara.utils.multipartitions import MULTIPARTITIONS
from dumpyara.utils.partitions import can_be_partition, extract_partition
import fnmatch
from os import walk
from pathlib import Path
from sebaubuntu_libs.liblogging import LOGI
from sebaubuntu_libs.libreorder import strcoll_files_key
from shutil import unpack_archive
from tempfile import TemporaryDirectory

class Dumpyara:
	"""
	A class representing an Android dump
	"""
	def __init__(self, file: Path, output_path: Path) -> None:
		"""Initialize dumpyara class."""
		self.file = file
		self.output_path = output_path

		# Output folder
		self.path = self.output_path / self.file.stem
		self.files_list = []

		# Make output dir
		self.path.mkdir(parents=True)

		# Create a temporary directory where we will extract the images
		self.raw_images_tempdir = TemporaryDirectory()
		self.raw_images_tempdir_path = Path(self.raw_images_tempdir.name)
		self.raw_images_tempdir_files_list = []

		LOGI("Step 1 - Extracting package")
		unpack_archive(self.file, self.raw_images_tempdir_path)
		self.update_raw_images_tempdir_files_list()

		LOGI("Step 2 - Checking multipartition images")
		for pattern, func in MULTIPARTITIONS.items():
			match = fnmatch.filter([str(file) for file in self.raw_images_tempdir_files_list], pattern)
			if not match:
				continue

			for file in match:
				multipart_image = self.raw_images_tempdir_path / file
				LOGI(f"Found multipartition image: {multipart_image.name}")
				func(multipart_image, self.raw_images_tempdir_path)
				self.update_raw_images_tempdir_files_list()

		LOGI("Step 3 - Extracting partitions")
		# Process all files
		for file in self.raw_images_tempdir_files_list:
			relative_file_path = file.relative_to(self.raw_images_tempdir_path)
			# Might have been deleted by previous step
			if not file.is_file():
				continue

			if can_be_partition(file):
				extract_partition(file, self.path)
			else:
				LOGI(f"Skipping {relative_file_path}")

		LOGI("Step 4 - Finalizing")
		# Update files list
		self.files_list.extend(sorted(self.get_recursive_files_list(self.path, relative=True),
		                              key=strcoll_files_key))

		# Create all_files.txt
		LOGI("Creating all_files.txt")
		(self.path / "all_files.txt").write_text("\n".join([str(file) for file in self.files_list]))

		# We don't need raw images anymore
		self.raw_images_tempdir.cleanup()
		self.raw_images_tempdir_files_list.clear()

	@staticmethod
	def get_recursive_files_list(path: Path, relative=False):
		for currentpath, _, files in walk(path):
			for file in files:
				file_path = Path(currentpath) / file
				if relative:
					file_path = file_path.relative_to(path)

				yield file_path

	def update_raw_images_tempdir_files_list(self):
		self.raw_images_tempdir_files_list.clear()
		self.raw_images_tempdir_files_list.extend(
				self.get_recursive_files_list(self.raw_images_tempdir_path))
