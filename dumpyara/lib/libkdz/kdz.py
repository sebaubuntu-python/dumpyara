#!/usr/bin/env python
#
# SPDX-FileCopyrightText: 2016 Elliott Mitchell <ehem+android@m5p.com>
# SPDX-FileCopyrightText: 2013 IOMonster (thecubed on XDA)
# SPDX-License-Identifier: GPL-3.0-or-later
#

from __future__ import absolute_import
from __future__ import print_function
import sys
from struct import Struct
from collections import OrderedDict
from dumpyara.lib.libkdz import dz


class KDZFile(dz.DZStruct):
	"""
	LGE KDZ File tools
	"""


	_dz_length = 272
	_dz_header = b"\x28\x05\x00\x00"b"\x24\x38\x22\x25"

	# Format string dict
	#   itemName is the new dict key for the data to be stored under
	#   formatString is the Python formatstring for struct.unpack()
	#   collapse is boolean that controls whether extra \x00 's should be stripped
	# Example:
	#   ('itemName', ('formatString', collapse))
	_dz_format_dict = OrderedDict([
		('name',	('256s', True)),
		('length',	('Q',    False)),
		('offset',	('Q',    False)),
	])


	def __init__(self):
		"""
		Initializer for KDZFile, gets DZStruct to fill remaining values
		"""
		super(KDZFile, self).__init__(KDZFile)

