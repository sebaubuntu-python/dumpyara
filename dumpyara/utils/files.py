#
# Copyright (C) 2023 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from os import chmod, walk, unlink
try:
	from os import chflags
except Exception:
	chflags = lambda *args, **kwargs: None
from pathlib import Path
from shutil import rmtree

def get_recursive_files_list(path: Path, relative: bool = False, as_str: bool = False):
	for currentpath, _, files in walk(path):
		for file in files:
			file_path = Path(currentpath) / file
			if relative:
				file_path = file_path.relative_to(path)

			yield str(file_path) if as_str else file_path

def rmtree_recursive(name: Path):
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
					rmtree_recursive(path)
			except FileNotFoundError:
				pass
		elif issubclass(exc_info[0], FileNotFoundError):
			pass
		else:
			raise

	rmtree(str(name), onerror=onerror)
