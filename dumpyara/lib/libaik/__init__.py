from dumpyara.lib.liblogging import LOGD, LOGI
from git import Repo
from pathlib import Path
from platform import system
from shutil import which
from subprocess import check_output, STDOUT, CalledProcessError
from tempfile import TemporaryDirectory

AIK_REPO = "https://github.com/SebaUbuntu/AIK-Linux-mirror"

ALLOWED_OS = [
	"Linux",
	"Darwin",
]

class AIKImageInfo:
	def __init__(self,
	             kernel: Path,
	             dt_image: Path,
	             dtb_image: Path,
	             dtbo_image: Path,
	             ramdisk: Path,
	             base_address: int,
	             board_name: str,
	             cmdline: str,
	             header_version: str,
	             recovery_size: int,
	             pagesize: int,
	             ramdisk_compression: str,
	             ramdisk_offset: int,
	             tags_offset: int,
	            ):
		self.kernel = kernel
		self.dt_image = dt_image
		self.dtb_image = dtb_image
		self.dtbo_image = dtbo_image
		self.ramdisk = ramdisk
		self.base_address = base_address
		self.board_name = board_name
		self.cmdline = cmdline
		self.header_version = header_version
		self.recovery_size = recovery_size
		self.pagesize = pagesize
		self.ramdisk_compression = ramdisk_compression
		self.ramdisk_offset = ramdisk_offset
		self.tags_offset = tags_offset

	def __str__(self):
		return (
			f"base address: {self.base_address}\n"
			f"board name: {self.board_name}\n"
			f"cmdline: {self.cmdline}\n"
			f"header version: {self.header_version}\n"
			f"recovery size: {self.recovery_size}\n"
			f"page size: {self.pagesize}\n"
			f"ramdisk compression: {self.ramdisk_compression}\n"
			f"ramdisk offset: {self.ramdisk_offset}\n"
			f"tags offset: {self.tags_offset}\n"
		)

class AIKManager:
	"""
	This class is responsible for dealing with AIK tasks
	such as cloning, updating, and extracting recovery images.
	"""

	def __init__(self):
		"""Initialize AIKManager class."""
		if system() not in ALLOWED_OS:
			raise NotImplementedError(f"{system()} is not supported")

		# Check whether cpio package is installed
		if which("cpio") is None:
			raise RuntimeError("cpio package is not installed")

		self.tempdir = TemporaryDirectory()
		self.path = Path(self.tempdir.name)

		self.images_path = self.path / "split_img"
		self.ramdisk_path = self.path / "ramdisk"

		LOGI("Cloning AIK...")
		Repo.clone_from(AIK_REPO, self.path)

	def extract(self, image: Path):
		"""Extract recovery image."""
		image_prefix = image.name

		try:
			process = self._execute_script("unpackimg.sh", image)
		except CalledProcessError as e:
			returncode = e.returncode
			output = e.output
		else:
			returncode = 0
			output = process

		if returncode != 0:
			LOGD(output)
			raise RuntimeError(f"AIK extraction failed, return code {returncode}")

		return self.get_current_extracted_info(image_prefix)

	def get_current_extracted_info(self, prefix: str):
		kernel = self.get_extracted_info(prefix, "kernel")
		kernel = kernel if kernel.is_file() else None
		dt_image = self.get_extracted_info(prefix, "dt")
		dt_image = dt_image if dt_image.is_file() else None
		dtb_image = self.get_extracted_info(prefix, "dtb")
		dtb_image = dtb_image if dtb_image.is_file() else None
		dtbo_image = None
		for name in ["dtbo", "recovery_dtbo"]:
			_dtbo_image = self.get_extracted_info(prefix, name)
			if _dtbo_image.is_file():
				dtbo_image = _dtbo_image
		ramdisk = self.ramdisk_path if self.ramdisk_path.is_dir() else None

		return AIKImageInfo(
			kernel=kernel,
			dt_image=dt_image,
			dtb_image=dtb_image,
			dtbo_image=dtbo_image,
			ramdisk=ramdisk,
			base_address=self.read_recovery_file(prefix, "base"),
			board_name=self.read_recovery_file(prefix, "board"),
			cmdline=self.read_recovery_file(prefix, "cmdline"),
			header_version=self.read_recovery_file(prefix, "header_version", default="0"),
			recovery_size=self.read_recovery_file(prefix, "origsize"),
			pagesize=self.read_recovery_file(prefix, "pagesize"),
			ramdisk_compression=self.read_recovery_file(prefix, "ramdiskcomp"),
			ramdisk_offset=self.read_recovery_file(prefix, "ramdisk_offset"),
			tags_offset=self.read_recovery_file(prefix, "tags_offset"),
		)

	def read_recovery_file(self, prefix: str, fragment: str, default: str = None) -> str:
		file = self.get_extracted_info(prefix, fragment)
		return file.read_text().splitlines()[0].strip() if file.exists() else default

	def get_extracted_info(self, prefix: str, fragment: str) -> Path:
		return self.images_path / f"{prefix}-{fragment}"

	def cleanup(self):
		return self._execute_script("cleanup.sh")

	def _execute_script(self, script: str, *args):
		command = [self.path / script, "--nosudo", *args]
		return check_output(command, stderr=STDOUT, universal_newlines=True)
