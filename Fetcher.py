# -*- coding: utf-8 -*-
"""
    Fetcher.py - fetching of pages from geocaching.com.
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
import urllib

class Fetcher(object):
    def __init__(self, GCparser):
        self.log  = logging.getLogger("GCparser.Fetch")
        self.GCparser = GCparser

        self.headers = []
        self.headers.append(("User-agent", "Mozilla/5.0"))
        self.headers.append(("Accept", "text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8"))
        self.headers.append(("Accept-Language", "en-us,en;q=0.5"))
        self.headers.append(("Accept-Charset", "utf-8,*;q=0.5"))

        self.lastFetch = 0 #TODO: fetch restrictions


    def fetch(self, url, authenticate = False, data = None):
        """Fetch page"""
        self.log.debug("Fetching page '%s'." % url)
        if authenticate:
            cookies = self.GCparser.auth.getCookies()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
        else:
            opener = urllib.request.build_opener()

        opener.addheaders = self.headers

        if data is not None:
            return opener.open(url, urllib.parse.urlencode(data))
        else:
            return opener.open(url)