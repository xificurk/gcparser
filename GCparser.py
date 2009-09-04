# -*- coding: utf-8 -*-
"""
    GCparser.py - GCparser main class.
    Copyright (C) 2009 Petr Morávek

    This file is part of GCparser.

    GCparser is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 2 of the License, or
    (at your option) any later version.

    GCparser is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License along
    with this program; if not, write to the Free Software Foundation, Inc.,
    51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
"""

import logging
from Authenticator import Authenticator
from Fetcher import Fetcher
import sys

class GCparser(object):
    def __init__(self, username = None, password = None, dataDir = "~/.geocaching/parser/"):
        self.log = logging.getLogger("GCparser")

        self.auth  = Authenticator(self, username, password, dataDir)
        self.fetch = Fetcher(self)

    def die(self):
        """Unrecoverable error, terminate application"""
        sys.exit()