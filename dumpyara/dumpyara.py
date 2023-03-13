#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

import fnmatch
from os import chmod, walk, unlink
try:
	from os import chflags
except Exception:
	chflags = lambda *args, **kwargs: None
from pathlib import Path
from sebaubuntu_libs.liblogging import LOGI
from sebaubuntu_libs.libreorder import strcoll_files_key
from shutil import move, rmtree, unpack_archive
from typing import List

from dumpyara.utils.multipartitions import MULTIPARTITIONS
from dumpyara.utils.partitions import (
    correct_ab_filenames,
	fix_aliases,
	extract_partitions,
	prepare_raw_images,
)
from dumpyara.utils.sparsed_images import prepare_sparsed_images

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

		LOGI("Step 1 - Extracting archive")
		# Create a temporary directory where we will extract the archive
		self.extracted_archive_tempdir_path = self.path / "temp_extracted_archive"
		self.extracted_archive_tempdir_path.mkdir()
		self.extracted_archive_tempdir_files_list: List[Path] = []

		# Extract the archive
		unpack_archive(self.file, self.extracted_archive_tempdir_path)

		# Flatten the folder
		for file in self.get_recursive_files_list(self.extracted_archive_tempdir_path):
			if file == self.extracted_archive_tempdir_path / file.name:
				continue
			move(str(file), self.extracted_archive_tempdir_path)
		self.update_extracted_archive_tempdir_files_list()

		LOGI("Step 2 - Preparing partition images")
		# Create a temporary directory where we will keep the raw images
		self.raw_images_tempdir_path = self.path / "temp_raw_images"
		self.raw_images_tempdir_path.mkdir()

		# Check for sparsed images
		prepare_sparsed_images(self.extracted_archive_tempdir_path)
		self.update_extracted_archive_tempdir_files_list()

		# Check for multipartitions
		for pattern, func in MULTIPARTITIONS.items():
			match = fnmatch.filter(self.extracted_archive_tempdir_files_list, pattern)
			if not match:
				continue

			for file in match:
				multipart_image = self.extracted_archive_tempdir_path / file
				LOGI(f"Found multipartition image: {multipart_image.name}")
				func(multipart_image, self.raw_images_tempdir_path)

		# Check for partitions
		prepare_raw_images(self.extracted_archive_tempdir_path, self.raw_images_tempdir_path)

		# Fix slotted filenames if needed
		correct_ab_filenames(self.raw_images_tempdir_path)

		# Fix aliases
		fix_aliases(self.raw_images_tempdir_path)

		# We don't need extracted files anymore
		self.rmtree(self.extracted_archive_tempdir_path)
		self.extracted_archive_tempdir_files_list.clear()

		LOGI("Step 3 - Extracting partitions")
		extract_partitions(self.raw_images_tempdir_path, self.path)

		# We don't need raw images anymore
		self.rmtree(self.raw_images_tempdir_path)

		LOGI("Step 4 - Finalizing")
		# Update files list
		self.files_list.extend(sorted(self.get_recursive_files_list(self.path, relative=True),
		                              key=strcoll_files_key))

		# Create all_files.txt
		LOGI("Creating all_files.txt")
		(self.path / "all_files.txt").write_text(
			"\n".join([str(file) for file in self.files_list]) + "\n")

	@staticmethod
	def get_recursive_files_list(path: Path, relative: bool = False, as_str: bool = False):
		for currentpath, _, files in walk(path):
			for file in files:
				file_path = Path(currentpath) / file
				if relative:
					file_path = file_path.relative_to(path)

				yield str(file_path) if as_str else file_path

	def update_extracted_archive_tempdir_files_list(self):
		self.extracted_archive_tempdir_files_list.clear()
		self.extracted_archive_tempdir_files_list.extend(
				self.get_recursive_files_list(self.extracted_archive_tempdir_path, True, True))

	@classmethod
	def rmtree(cls, name: Path):
		def onerror(func, path, exc_info):
			if issubclass(exc_info[0], PermissionError):
				def resetperms(path):
					chflags(path, 0)
					chmod(path, 0o700)

				try:
					if path != name:
						resetperms(name.parent)
					resetperms(path)

					try:
						unlink(path)
					# PermissionError is raised on FreeBSD for directories
					except (IsADirectoryError, PermissionError):
						cls.rmtree(path)
				except FileNotFoundError:
					pass
			elif issubclass(exc_info[0], FileNotFoundError):
				pass
			else:
				raise

		rmtree(str(name), onerror=onerror)
