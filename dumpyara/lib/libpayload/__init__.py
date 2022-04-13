import hashlib
import os
from pathlib import Path
import struct
import subprocess
from google.protobuf import message

# from https://android.googlesource.com/platform/system/update_engine/+/refs/heads/master/scripts/update_payload/
from . import update_metadata_pb2

BRILLO_MAJOR_PAYLOAD_VERSION = 2

class PayloadError(Exception):
	pass

class Payload(object):
	class _PayloadHeader(object):
		_MAGIC = b'CrAU'

		def __init__(self):
			self.version = None
			self.manifest_len = None
			self.metadata_signature_len = None
			self.size = None

		def ReadFromPayload(self, payload_file):
			magic = payload_file.read(4)
			if magic != self._MAGIC:
				raise PayloadError(f'Invalid payload magic: {magic}')
			self.version = struct.unpack('>Q', payload_file.read(8))[0]
			self.manifest_len = struct.unpack('>Q', payload_file.read(8))[0]
			self.size = 20
			self.metadata_signature_len = 0
			if self.version != BRILLO_MAJOR_PAYLOAD_VERSION:
				raise PayloadError(f'Unsupported payload version ({self.version})')
			self.size += 4
			self.metadata_signature_len = struct.unpack('>I', payload_file.read(4))[0]

	def __init__(self, payload_file):
		self.payload_file = payload_file
		self.header = None
		self.manifest = None
		self.data_offset = None
		self.metadata_signature = None
		self.metadata_size = None

	def _ReadManifest(self):
		return self.payload_file.read(self.header.manifest_len)

	def _ReadMetadataSignature(self):
		self.payload_file.seek(self.header.size + self.header.manifest_len)
		return self.payload_file.read(self.header.metadata_signature_len)

	def ReadDataBlob(self, offset, length):
		self.payload_file.seek(self.data_offset + offset)
		return self.payload_file.read(length)

	def Init(self):
		self.header = self._PayloadHeader()
		self.header.ReadFromPayload(self.payload_file)
		manifest_raw = self._ReadManifest()
		self.manifest = update_metadata_pb2.DeltaArchiveManifest()
		try:
			self.manifest.ParseFromString(manifest_raw)
		except message.DecodeError as parse_error:
			print(f"[WARN] Cannot deserialize Protobuf. Reason: {parse_error}")
		metadata_signature_raw = self._ReadMetadataSignature()
		if metadata_signature_raw:
			self.metadata_signature = update_metadata_pb2.Signatures()
			self.metadata_signature.ParseFromString(metadata_signature_raw)
		self.metadata_size = self.header.size + self.header.manifest_len
		self.data_offset = self.metadata_size + self.header.metadata_signature_len

def decompress_payload(command, data, size, hash):
	p = subprocess.Popen([command, '-'], stdout=subprocess.PIPE, stdin=subprocess.PIPE)
	r = p.communicate(data)[0]
	if len(r) != size:
		print(f"Unexpected size {len(r)} {size}")
	elif hashlib.sha256(data).digest() != hash:
		print("Hash mismatch")
	return r

def parse_payload(payload_f, partition, out_f):
	BLOCK_SIZE = 4096
	for operation in partition.operations:
		e = operation.dst_extents[0]
		data = payload_f.ReadDataBlob(operation.data_offset, operation.data_length)
		out_f.seek(e.start_block * BLOCK_SIZE)
		if operation.type == update_metadata_pb2.InstallOperation.REPLACE:
			out_f.write(data)
		elif operation.type == update_metadata_pb2.InstallOperation.REPLACE_XZ:
			r = decompress_payload('xzcat', data, e.num_blocks * BLOCK_SIZE, operation.data_sha256_hash)
			out_f.write(r)
		elif operation.type == update_metadata_pb2.InstallOperation.REPLACE_BZ:
			r = decompress_payload('bzcat', data, e.num_blocks * BLOCK_SIZE, operation.data_sha256_hash)
			out_f.write(r)
		elif operation.type == update_metadata_pb2.InstallOperation.ZERO:
			out_f.write(b'\x00' * (e.num_blocks * BLOCK_SIZE))
		else:
			raise PayloadError(f'Unhandled operation type ({operation.type} - {update_metadata_pb2.InstallOperation.Type.Name(operation.type)})')

def extract_android_ota_payload(filename: Path, output_dir: Path):
	payload_file = open(filename, 'rb')

	payload = Payload(payload_file)
	payload.Init()

	for p in payload.manifest.partitions:
		name = f"{p.partition_name}.img"
		print(f"Extracting '{name}'")
		fname = output_dir / name
		out_f = open(fname, 'wb')
		try:
			parse_payload(payload, p, out_f)
		except PayloadError as e:
			print(f'Failed: {e}')
			out_f.close()
			os.unlink(fname)
