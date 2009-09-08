# -*- coding: utf-8 -*-
"""
    Parsers.py - standard parsesr of geocaching.com.
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



class Cache(BaseParser):
    def __init__(self, GCparser, guid = None, waypoint = None, logs = False):
        BaseParser.__init__(self, GCparser)
        self.log = logging.getLogger("GCparser.Cache")
        self.details = None
        self.waypoint = waypoint
        self.guid = guid

        if guid is None and waypoint is None:
            self.log.critical("No guid or waypoint given - don't know what to parse.")
            self.GCparser.die()

        self.url = "http://www.geocaching.com/seek/cache_details.aspx?pf=y&numlogs=&decrypt=y"
        if guid is not None:
            self.url = self.url + "&guid=%s" % guid
        else:
            self.url = self.url + "&wp=%s" % waypoint

        if logs:
            self.url = self.url + "&log=y"
            self.logs = None
        else:
            self.url = self.url + "&log="
            self.logs = False


    def load(self):
        """Loads data from webpage"""
        if self.data is None:
            web = self.GCparser.fetch.fetch(self.url, authenticate=True)
            self.read(web)
            if not self.checkLogin():
                self.GCparser.auth.login()
                self.load()


    def getDetails(self):
        """returns parsed details of this cache"""
        if self.details is not None:
            return self.details

        self.load()

        self.details = {}

        match = re.search("<span id=['\"]ErrorText['\"][^>]*><p>Sorry, the owner of this listing has made it viewable to subscribers only", self.data, re.I)
        if match:
            self.log.info("Subscribers only cache at '%s'." % self.url)
            if self.guid is not None:
                self.details["guid"] = self.guid
            elif self.waypoint is not None:
                self.details["waypoint"] = self.waypoint
            return self.details

        self.details["disabled"] = 0
        self.details["archived"] = 0
        match = re.search("<span id=['\"]ErrorText['\"][^>]*><strong>Cache Issues:</strong><ul><font[^>]*><li>This cache (has been archived|is temporarily unavailable)[^<]*</li>", self.data, re.I)
        if match:
            if match.group(1) == "has been archived":
                self.details["archived"] = 1
                self.log.log(5, "archived = %d" % self.details["archived"])
            self.details["disabled"] = 1
            self.log.log(5, "disabled = %d" % self.details["disabled"])

        match = re.search("GC[A-Z0-9]+", self.data)
        if match:
            self.details["waypoint"] = match.group(0)
            self.log.log(5, "waypoint = %s" % self.details["waypoint"])
        else:
            self.details["waypoint"] = ""
            self.log.error("Waypoint not found.")

        match = re.search("<span id=['\"]CacheName['\"]>([^<]+)</span>", self.data, re.I)
        if match:
            self.details["name"] = self.unescape(match.group(1)).strip()
            self.log.log(5, "name = %s" % self.details["name"])
        else:
            self.details["name"] = ""
            self.log.error("Name not found.")

        match = re.search("<span id=['\"]DateHidden['\"]>([0-9]+)/([0-9]+)/([0-9]+)</span>", self.data, re.I)
        if match:
            self.details["hidden"] = "%4d-%02d-%02d" % (int(match.group(3)), int(match.group(1)), int(match.group(2)))
            self.log.log(5, "hidden = %s" % self.details["hidden"])
        else:
            self.details["hidden"] = "0000-00-00"
            self.log.error("Hidden date not found.")

        match = re.search("<span id=['\"]CacheOwner['\"]>([^<]+)<br />Size: ([^<]+)<br />by <a href=['\"]http://www.geocaching.com/profile/\?guid=([a-z0-9-]+)&wid=([a-z0-9-]+)[^'\"]*['\"]>([^<]+)</a></span>", self.data, re.I)
        if match:
            self.details["type"] = self.unescape(match.group(1)).strip()
            self.details["size"] = self.unescape(match.group(2)).strip()
            self.details["guid"] = self.unescape(match.group(4))
            self.details["owner"] = self.unescape(match.group(5)).strip()
            self.details["owner_id"] = self.unescape(match.group(3))
            self.log.log(5, "guid = %s" % self.details["guid"])
            self.log.log(5, "type = %s" % self.details["type"])
            self.log.log(5, "size = %s" % self.details["size"])
            self.log.log(5, "owner = %s" % self.details["owner"])
            self.log.log(5, "owner_id = %s" % self.details["owner_id"])
        else:
            self.details["type"] = ""
            self.details["size"] = ""
            self.details["guid"] = ""
            self.details["owner"] = ""
            self.details["owner_id"] = ""
            self.log.error("Type, size, guid, owner, owner_id not found.")

        match = re.search("<span id=['\"]Difficulty['\"]><img src=['\"]http://www.geocaching.com/images/stars/[^\"']*['\"] alt=['\"]([0-9.]+) out of 5['\"]", self.data, re.I)
        if match:
            self.details["difficulty"] = float(match.group(1))
            self.log.log(5, "difficulty = %.1f" % self.details["difficulty"])
        else:
            self.details["difficulty"] = 0
            self.log.error("Difficulty not found.")

        match = re.search("<span id=['\"]Terrain['\"]><img src=['\"]http://www.geocaching.com/images/stars/[^\"']*['\"] alt=['\"]([0-9.]+) out of 5['\"]", self.data, re.I)
        if match:
            self.details["terrain"] = float(match.group(1))
            self.log.log(5, "terrain = %.1f" % self.details["terrain"])
        else:
            self.details["terrain"] = 0
            self.log.error("Terrain not found.")

        match = re.search("<span id=['\"]LatLon['\"][^>]*>([NS]) ([0-9]+)° ([0-9.]+) ([WE]) ([0-9]+)° ([0-9.]+)</span>", self.data, re.I)
        if match:
            self.details["lat"] = float(match.group(2)) + float(match.group(3))/60
            if match.group(1) == "S":
                self.details["lat"] = -self.details["lat"]
            self.details["lon"] = float(match.group(5)) + float(match.group(6))/60
            if match.group(4) == "W":
                self.details["lon"] = -self.details["lon"]
            self.log.log(5, "lat = %f" % self.details["lat"])
            self.log.log(5, "lon = %f" % self.details["lon"])
        else:
            self.details["lat"] = 0
            self.details["lon"] = 0
            self.log.error("Lat, lon not found.")

        self.details["province"] = ""
        match = re.search("<span id=['\"]Location['\"]>In (([^,<]+), )?([^<]+)</span>", self.data, re.I)
        if match:
            self.details["country"] = self.unescape(match.group(3)).strip()
            if match.group(2):
                self.details["province"] = self.unescape(match.group(2)).strip()
                self.log.log(5, "province = %s" % self.details["province"])
            self.log.log(5, "country = %s" % self.details["country"])
        else:
            self.details["country"] = ""
            self.log.error("Country not found.")

        match = re.search("<span id=['\"]ShortDescription['\"]>(.*?)</span>\s\s\s\s", self.data, re.I|re.S)
        if match:
            self.details["shortDesc"] = self.cleanHTML(match.group(1))
            self.log.log(5, "shortDesc = %s..." % self.details["shortDesc"].replace("\n"," ")[0:50])
        else:
            self.details["shortDesc"] = ""

        match = re.search("<span id=['\"]LongDescription['\"]>(.*?)</span>\s\s\s\s", self.data, re.I|re.S)
        if match:
            self.details["longDesc"] = self.cleanHTML(match.group(1))
            self.log.log(5, "longDesc = %s..." % self.details["longDesc"].replace("\n"," ")[0:50])
        else:
            self.details["longDesc"] = ""

        match = re.search("<span id=['\"]Hints['\"][^>]*>(.*)</span>", self.data, re.I)
        if match:
            self.details["hint"] = self.unescape(match.group(1).replace("<br>", "\n")).strip()
            self.log.log(5, "hint = %s..." % self.details["hint"].replace("\n"," ")[0:50])
        else:
            self.details["hint"] = ""

        match = re.search("<b>Attributes</b><br/><table.*?</table>([^<]+)", self.data, re.I)
        if match:
            self.details["attributes"] = match.group(1).strip()
            self.log.log(5, "attributes = %s" % self.details["attributes"])
        else:
            self.details["attributes"] = ""

        self.details["inventory"] = {}
        match = re.search("<img src=['\"]\.\./images/WptTypes/sm/tb_coin\.gif['\"][^>]*>[^<]*<b>Inventory</b>.*?<table[^>]*>(.*?)<tr>[^<]*<td[^>]*>[^<]*<a[^>]*>See the history</a>", self.data, re.I|re.S)
        if match:
            for part in match.group(1).split("</tr>"):
                match = re.search("<a href=['\"]http://www.geocaching.com/track/details.aspx\?guid=([a-z0-9-]+)['\"]>([^<]+)</a>", part, re.I)
                if match:
                    self.details["inventory"][match.group(1)] = self.unescape(match.group(2).strip())
            self.log.log(5, "inventory = %s" % self.details["inventory"])

        self.details["visits"] = {}
        match = re.search("<span id=\"lblFindCounts\"[^>]*><table[^>]*>(.*?)</table></span>", self.data, re.I)
        if match:
            for part in match.group(1).split("</td><td>"):
                match = re.search("<img[^>]*alt=\"([^\"]+)\"[^>]*/>([0-9]+)", part, re.I)
                if match:
                    self.details["visits"][match.group(1)] = int(match.group(2))
            self.log.log(5, "visits = %s" % self.details["visits"])

        return self.details



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
            self.read(web)
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
            for line in self.data.splitlines():
                match = re.search("<td[^>]*><img[^>]*Found it[^>]*></td>", line, re.I)
                if match:
                    cache = {"sequence":total-len(self.cacheList)}
                    self.log.debug("NEW cache record")
                    self.log.log(5, "sequence = %d" % cache["sequence"])

                match = re.search("<td[^>]*>([0-9]+)/([0-9]+)/([0-9]+)</td>", line, re.I)
                if match:
                    cache["f_date"] = "%4d-%02d-%02d" % (int(match.group(3)), int(match.group(1)), int(match.group(2)))
                    self.log.log(5, "f_date = %s" % cache["f_date"])

                match = re.search("<td[^>]*><a href=['\"]http://www.geocaching.com/seek/cache_details.aspx\?guid=([a-z0-9-]+)['\"][^>]*>(<font color=\"red\">)?(<strike>)?([^<]+)(</strike>)?[^<]*(</font>)?[^<]*</a>[^<]*</td>", line, re.I)
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
                    self.log.log(5, "guid = %s" % cache["guid"])
                    self.log.log(5, "name = %s" % self.unescape(cache["name"]))
                    self.log.log(5, "disabled = %d" % cache["disabled"])
                    self.log.log(5, "archived = %d" % cache["archived"])

                match = re.search("<td[^>]*>\[<a href=['\"]http://www.geocaching.com/seek/log.aspx\?LUID=([a-z0-9-]+)['\"][^>]*>visit log</a>\]</td>", line, re.I)
                if match:
                    cache["f_luid"] = match.group(1)
                    self.log.log(5, "f_luid = %s" % cache["f_luid"])
                    self.log.debug("END of cache record '%s'" % cache["name"])
                    self.cacheList.append(cache)

        return self.cacheList


    def getCount(self):
        """returns total count of found logs"""
        if self.count is not None:
            return self.count

        self.load()

        match = re.search("<p>([0-9]+) Results:</p>", self.data, re.I)
        if match:
            self.count = int(match.group(1))
        else:
            self.count = 0

        return self.count
