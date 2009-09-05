# -*- coding: utf-8 -*-
"""
    Parsers/BaseParsers.py - parent for all parsers.
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
import re
from html.parser import HTMLParser

logging.addLevelName(5, "PARSER")

class BaseParser(object):
    def __init__(self, GCparser):
        self.GCparser = GCparser
        self.unescape = HTMLParser().unescape
        self.data     = None

    def read(self, web):
        """Parses web resource"""
        self.data = web.read().decode("utf-8")

    def checkLogin(self):
        """Checks the line for not logged in error"""
        logged = True
        if self.data is not None:
            for line in self.data.splitlines():
                if line.find("You are not Logged in.") != -1:
                    logged = False
                    break
        return logged

    def cleanHTML(self, text):
        """Cleans text from HTML markup and unescapes entities"""
        text = text.replace("\r", " ")
        text = text.replace("\n", " ")

        text = re.sub("<p[^>]*>", "\n** ", text, flags = re.I)
        text = re.sub("<br[^>]*>", "\n", text, flags = re.I)
        text = re.sub("<li[^>]*>", "\n - ", text, flags = re.I)

        text = re.sub("</?h[0-9][^>]*>", "\n", text, flags = re.I)

        text = re.sub("<img[^>]*alt=['\"]([^'\"]+)['\"][^>]*>", "[img \\1]", text, flags = re.I)
        text = re.sub("<img[^>]*>", "[img]", text, flags = re.I)

        text = re.sub("<[^>]*>", "", text)

        # Escape entities
        text = self.unescape(text)

        # Remove unnecessary spaces
        text = re.sub("^\s+", "", text, flags = re.M)
        text = re.sub("\s+$", "", text, flags = re.M)
        text = re.sub("^\s*$\n", "", text, flags = re.M)
        text = re.sub("\s\s+", " ", text)

        return text
