#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from dumpyara.lib.liblogging import LOGI
from dumpyara.lib.liblpunpack import LpUnpack
from dumpyara.lib.libpayload import extract_android_ota_payload
from dumpyara.utils.partitions import can_be_partition, extract_partition
import fnmatch
from os import walk
from pathlib import Path
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

		# Create working folder dir
		self.output_path.mkdir(exist_ok=True, parents=True)

		# Create a temporary directory where we will extract the images
		self.tempdir = TemporaryDirectory()
		self.tempdir_path = Path(self.tempdir.name)

		# Output folder
		self.path = self.output_path / self.file.stem
		self.path.mkdir()

		self.fileslist = []

		LOGI("Extracting package...")
		unpack_archive(self.file, self.tempdir_path)
		self.update_tempdir_files_list()

		# Extract payload.bin if it exists
		# It contains all the partitions that we are interested in
		payload_match = fnmatch.filter([str(file) for file in self.fileslist], "*payload.bin*")
		if payload_match:
			LOGI("Payload partition detected, first extracting it")
			extract_android_ota_payload(self.tempdir_path / payload_match[0], self.tempdir_path)
			self.update_tempdir_files_list()

		# Extract super first if it exists
		# It contains all the partitions that we are interested in
		super_match = fnmatch.filter([str(file) for file in self.fileslist], "*super.img*")
		if super_match:
			LOGI("Super partition detected, first extracting it")
			LpUnpack(SUPER_IMAGE=self.tempdir_path / super_match[0], OUTPUT_DIR=self.tempdir_path).unpack()
			self.update_tempdir_files_list()

		# Process all files
		for file in self.fileslist:
			relative_file_path = file.relative_to(self.tempdir_path)
			# Might have been deleted by previous step
			if not file.is_file():
				continue

			if can_be_partition(file):
				extract_partition(file, self.path)
			else:
				LOGI(f"Skipping {relative_file_path}")

		# We don't need artifacts anymore
		self.tempdir.cleanup()

		# Create all_files.txt
		LOGI("Creating all_files.txt")
		with open(self.path / "all_files.txt", "w") as f:
			f.write("\n".join([str(file) for file in self.get_recursive_files_list(self.path, relative=True)]))

	@staticmethod
	def get_recursive_files_list(path: Path, relative=False):
		files_list = []

		for currentpath, _, files in walk(path):
			for file in files:
				file_path = Path(currentpath) / file
				if relative:
					file_path = file_path.relative_to(path)
				files_list.append(file_path)

		return files_list

	def update_tempdir_files_list(self):
		self.fileslist.clear()
		self.fileslist.extend(self.get_recursive_files_list(self.tempdir_path))
