# -*- coding: utf-8 -*-
"""
    Parsers.py - parse data from webpages.
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
import sys

class BaseParser(object):
    def __init__(self, GCparser):
        self.GCparser = GCparser
        self.data     = None

    def readLines(self, web):
        """Parses web resource to list of lines"""
        self.data = web.read().decode("utf-8")
        self.data = self.data.splitlines()

    def checkLogin(self):
        """Checks the line for not logged in error"""
        logged = True
        if self.data is not None:
            for line in self.data:
                if line.find("You are not Logged in.") != -1:
                    logged = False
                    break
        return logged



class MyFinds(BaseParser):
    def __init__(self, GCparser):
        BaseParser.__init__(self, GCparser)
        self.log = logging.getLogger("GCparser.MyFinds")
        self.cacheList = None
        self.count     = None


    def load(self):
        """Loads data from webpage"""
        if self.data is None:
            web = self.GCparser.fetch.fetch("http://www.geocaching.com/my/logs.aspx?s=1&lt=2", authenticate=True)
            self.readLines(web)
            if not self.checkLogin():
                self.GCparser.auth.login()
                self.load()


    def getList(self):
        """returns parsed list of found caches"""
        if self.cacheList is not None:
            return self.cacheList

        self.load()

        total = self.getCount()
        self.cacheList = []

        if total > 0:
            """
                <td valign="top" align="left" height=16 width=16><img src='../images/icons/icon_smile.gif' width=16 height=16 border=0 alt='Found it'></td>
                <td valign="top" align="left" height=16>9/2/2009</td>
                <td valign="top" align="left" height=16  width=90%><A href="http://www.geocaching.com/seek/cache_details.aspx?guid=f83032d7-d60f-4f0d-bb1b-670287824e33"> Pardubice-mesto sportu c.8   </a>&nbsp;</td>
                <td valign="top" align="left" height=16 nowrap>Pardubicky kraj &nbsp;</td>
                <td valign="top" align="right" height=16 nowrap width=8%>[<a href='http://www.geocaching.com/seek/log.aspx?LUID=f315d6e1-127f-4173-860c-8aebda55521f' target=_blank>visit log</a>]</td>
            """
            for line in self.data:
                match = re.search("<td[^>]*><img[^>]*Found it[^>]*></td>", line)
                if match:
                    cache = {'sequence':total-len(self.cacheList)}
                    self.log.debug("NEW cache record")
                    self.log.debug("  sequence = %d" % cache['sequence'])

                match = re.search("<td[^>]*>([0-9]+)/([0-9]+)/([0-9]+)</td>", line)
                if match:
                    cache["f_date"] = "%4d-%02d-%02d" % (int(match.group(3)), int(match.group(1)), int(match.group(2)))
                    self.log.debug("  f_date = %s" % cache["f_date"])

                match = re.search("<td[^>]*><[Aa] href=['\"]http://www.geocaching.com/seek/cache_details.aspx\?guid=([a-z0-9-]+)['\"][^>]*>(<font color=\"red\">)?(<strike>)?([^<]+)(</strike>)?[^<]*(</font>)?[^<]*</a>[^<]*</td>", line)
                if match:
                    cache["guid"] = match.group(1)
                    cache["name"] = match.group(4).strip()
                    if match.group(3):
                        cache["disabled"] = 1
                    else:
                        cache["disabled"] = 0
                    if match.group(2):
                        cache["archived"] = 1
                    else:
                        cache["archived"] = 0
                    self.log.debug("  guid = %s" % cache["guid"])
                    self.log.debug("  name = %s" % cache["name"])
                    self.log.debug("  disabled = %d" % cache["disabled"])
                    self.log.debug("  archived = %d" % cache["archived"])

                match = re.search("<td[^>]*>\[<a href=['\"]http://www.geocaching.com/seek/log.aspx\?LUID=([a-z0-9-]+)['\"][^>]*>visit log</a>\]</td>", line)
                if match:
                    cache["f_luid"] = match.group(1)
                    self.log.debug("  f_luid = %s" % cache["f_luid"])
                    self.log.debug("END of cache record")
                    self.cacheList.append(cache)

        return self.cacheList


    def getCount(self):
        """returns total count of found logs"""
        if self.count is not None:
            return self.count

        self.load()

        for line in self.data:
            match = re.search("<p>([0-9]+) Results:</p>", line)
            if match:
                self.count = int(match.group(1))
                break
            if line.find("No results were found.") != -1:
                self.count = 0
                break

        return self.count