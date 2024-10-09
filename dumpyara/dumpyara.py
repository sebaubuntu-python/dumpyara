#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from pathlib import Path
from sebaubuntu_libs.liblogging import LOGI
from sebaubuntu_libs.libreorder import strcoll_files_key
from shutil import which

from dumpyara.lib.libsevenzip import SEVEN_ZIP_EXECUTABLE, P7ZIP_EXECUTABLE
from dumpyara.utils.files import get_recursive_files_list, rmtree_recursive
from dumpyara.steps.extract_archive import extract_archive
from dumpyara.steps.extract_images import extract_images
from dumpyara.steps.prepare_images import prepare_images

# Package name to package commands
REQUIRED_TOOLS = {
	"7-zip or p7zip": [SEVEN_ZIP_EXECUTABLE, P7ZIP_EXECUTABLE],
	"erofs-utils": ["fsck.erofs"],
	"android-sdk-libsparse-utils or platform-utils": ["simg2img"],
}

def dumpyara(file: Path, output_path: Path, debug: bool = False):
	"""Dump an Android firmware."""

	# Temporary directories
	extracted_archive_path = output_path / "temp_extracted_archive"
	raw_images_path = output_path / "temp_raw_images"

	# First, check if the necessary tools are installed
	for package, tools in REQUIRED_TOOLS.items():
		installed = any(which(tool) for tool in tools)

		if installed:
			continue

		raise RuntimeError(
			f"You are missing {tools[0]}, please install {package} from your distro's repositories"
		)

	try:
		# Make output and temporary directories
		output_path.mkdir(exist_ok=True)
		extracted_archive_path.mkdir()
		raw_images_path.mkdir()

		LOGI("Step 1 - Extracting archive")
		extract_archive(file, extracted_archive_path)

		LOGI("Step 2 - Preparing partition images")
		prepare_images(extracted_archive_path, raw_images_path)

		LOGI("Step 3 - Extracting partitions")
		extract_images(raw_images_path, output_path)

		# Make sure system folder exists and it's not empty
		assert (output_path / "system").exists(), "System folder doesn't exist"
		assert len(list((output_path / "system").iterdir())) > 0, "System folder is empty"

		LOGI("Step 4 - Finalizing")
		# Update files list
		files_list = sorted(
			get_recursive_files_list(output_path, relative=True),
			key=strcoll_files_key
		)

		# Create all_files.txt
		LOGI("Creating all_files.txt")
		(output_path / "all_files.txt").write_text(
			"\n".join([str(file) for file in files_list]) + "\n"
		)

		return output_path
	finally:
		if not debug:
			# Remove temporary directories if they exist
			if extracted_archive_path.exists():
				rmtree_recursive(extracted_archive_path)

			if raw_images_path.exists():
				rmtree_recursive(raw_images_path)
