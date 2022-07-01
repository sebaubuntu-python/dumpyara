from pathlib import Path
from struct import pack, unpack, calcsize

SPARSE_HEADER_MAGIC = 0xED26FF3A
SPARSE_HEADER_SIZE = 28
SPARSE_CHUNK_HEADER_SIZE = 12

class SparseHeader(object):
    def __init__(self, buffer):
        fmt = '<I4H4I'
        (
            self.magic,             # 0xed26ff3a
            self.major_version,     # (0x1) - reject images with higher major versions
            self.minor_versionm,    # (0x0) - allow images with higer minor versions
            self.file_hdr_sz,       # 28 bytes for first revision of the file format
            self.chunk_hdr_sz,      # 12 bytes for first revision of the file format
            self.blk_sz,            # block size in bytes, must be a multiple of 4 (4096)
            self.total_blks,        # total blocks in the non-sparse output image
            self.total_chunks,      # total chunks in the sparse input image
            self.image_checksum     # CRC32 checksum of the original data, counting "don't care"
        ) = unpack(fmt, buffer[0:calcsize(fmt)])


class SparseChunkHeader(object):
    """
        Following a Raw or Fill or CRC32 chunk is data.
        For a Raw chunk, it's the data in chunk_sz * blk_sz.
        For a Fill chunk, it's 4 bytes of the fill data.
        For a CRC32 chunk, it's 4 bytes of CRC32
     """
    def __init__(self, buffer):
        fmt = '<2H2I'
        (
            self.chunk_type,        # 0xCAC1 -> raw; 0xCAC2 -> fill; 0xCAC3 -> don't care */
            self.reserved1,
            self.chunk_sz,          # in blocks in output image * /
            self.total_sz,          # in bytes of chunk input file including chunk header and data * /
        ) = unpack(fmt, buffer[0:calcsize(fmt)])

class SparseImage(object):
    def __init__(self, fd):
        self._fd = fd
        self.header = None

    def check(self):
        self._fd.seek(0)
        self.header = SparseHeader(self._fd.read(SPARSE_HEADER_SIZE))
        return False if self.header.magic != SPARSE_HEADER_MAGIC else True

    def unsparse(self):
        if not self.header:
            self._fd.seek(0)
            self.header = SparseHeader(self._fd.read(SPARSE_HEADER_SIZE))
        chunks = self.header.total_chunks
        self._fd.seek(self.header.file_hdr_sz - SPARSE_HEADER_SIZE, 1)
        unsparse_file_dir = Path(self._fd.name).parent
        unsparse_file = Path(unsparse_file_dir / "{}.unsparse.img".format(Path(self._fd.name).stem))
        with open(str(unsparse_file), 'wb') as out:
            sector_base = 82528
            output_len = 0
            while chunks > 0:
                chunk_header = SparseChunkHeader(self._fd.read(SPARSE_CHUNK_HEADER_SIZE))
                sector_size = (chunk_header.chunk_sz * self.header.blk_sz) >> 9
                chunk_data_size = chunk_header.total_sz - self.header.chunk_hdr_sz
                if chunk_header.chunk_type == 0xCAC1:
                    if self.header.chunk_hdr_sz > SPARSE_CHUNK_HEADER_SIZE:
                        self._fd.seek(self.header.chunk_hdr_sz - SPARSE_CHUNK_HEADER_SIZE, 1)
                    data = self._fd.read(chunk_data_size)
                    len_data = len(data)
                    if len_data == (sector_size << 9):
                        out.write(data)
                        output_len += len_data
                        sector_base += sector_size
                else:
                    if chunk_header.chunk_type == 0xCAC2:
                        if self.header.chunk_hdr_sz > SPARSE_CHUNK_HEADER_SIZE:
                            self._fd.seek(self.header.chunk_hdr_sz - SPARSE_CHUNK_HEADER_SIZE, 1)
                        data = self._fd.read(chunk_data_size)
                        len_data = sector_size << 9
                        out.write(pack("B", 0) * len_data)
                        output_len += len(data)
                        sector_base += sector_size
                    else:
                        if chunk_header.chunk_type == 0xCAC3:
                            if self.header.chunk_hdr_sz > SPARSE_CHUNK_HEADER_SIZE:
                                self._fd.seek(self.header.chunk_hdr_sz - SPARSE_CHUNK_HEADER_SIZE, 1)
                            data = self._fd.read(chunk_data_size)
                            len_data = sector_size << 9
                            out.write(pack("B", 0) * len_data)
                            output_len += len(data)
                            sector_base += sector_size
                        else:
                            len_data = sector_size << 9
                            out.write(pack("B", 0) * len_data)
                            sector_base += sector_size
                chunks -= 1
        return unsparse_file
