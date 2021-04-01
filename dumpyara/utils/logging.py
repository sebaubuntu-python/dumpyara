#
# Copyright (C) 2022 Dumpyara Project
#
# SPDX-License-Identifier: GPL-3.0
#

from logging import basicConfig, INFO, DEBUG

def setup_logging(verbose=False):
	if verbose:
		basicConfig(format='[%(filename)s:%(lineno)s %(levelname)s] %(funcName)s: %(message)s',
					level=DEBUG)
	else:
		basicConfig(format='[%(levelname)s] %(message)s', level=INFO)
