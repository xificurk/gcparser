# -*- coding: utf-8 -*-
"""
    gcparser.py - simple library for parsing geocaching.com website.
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
from hashlib import md5
from html.parser import HTMLParser
import http.cookiejar as CJ
import os
import random
import re
import sys
import time
import urllib


class GCparser(object):
    def __init__(self, username = None, password = None, dataDir = "~/.geocaching/parser"):
        self.log = logging.getLogger("GCparser")

        self.auth    = Authenticator(self, username, password, dataDir)
        self.fetch   = Fetcher(self)
        self.parsers = {}
        # Register standard distribution parsers
        self.registerParser("myFinds", Parsers.MyFinds)
        self.registerParser("cache", Parsers.Cache)
        self.registerParser("editProfile", Parsers.EditProfile)


    def die(self):
        """Unrecoverable error, terminate application"""
        sys.exit()


    def registerParser(self, name, handler):
        """Register custom parser object"""
        self.parsers[name] = handler


    def parse(self, name, *args, **kwargs):
        """Call parser of the name"""
        return self.parsers[name](self, *args, **kwargs)



class Fetcher(object):
    def __init__(self, GCparser):
        self.log  = logging.getLogger("GCparser.Fetch")
        self.GCparser = GCparser

        self.headers = []
        self.headers.append(("User-agent", self.getRandomUA()))
        self.headers.append(("Accept", "text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8"))
        self.headers.append(("Accept-Language", "en-us,en;q=0.5"))
        self.headers.append(("Accept-Charset", "utf-8,*;q=0.5"))

        self.lastFetch  = 0
        self.fetchCount = 0


    def getRandomUA(self):
        """Generate random UA string - masking as Firefox 3.0.x"""
        system = random.randint(1,5)
        if system <= 1:
            system = "X11"
            systemversion = ["Linux i686", "Linux x86_64"]
        elif system <= 2:
            system = "Macintosh"
            systemversion = ["PPC Mac OS X 10.5"]
        else:
            system = "Windows"
            systemversion = ["Windows NT 5.1", "Windows NT 6.0", "Windows NT 6.1"]

        systemversion = systemversion[random.randint(0,len(systemversion)-1)]
        version = random.randint(1,13)
        date = "200907%02d%02d" % (random.randint(1, 31), random.randint(1,23))

        ua = "Mozilla/5.0 (%s; U; %s; en-US; rv:1.9.0.%d) Gecko/%s Firefox/3.0.%d" % (system, systemversion, version, date, version)

        return ua


    def wait(self):
        """Waits for random number of seconds to lessen the load on geocaching.com"""
        # 60 fetches in first minute => 60/1min
        if self.fetchCount < 60:
            sleeptime = 1
        # another 240 fetches in 10 minutes => 300/11min
        elif self.fetchCount < 300:
            sleeptime = random.randint(1,4)
        # another 300 fetches in 30 minutes => 600/41min
        elif self.fetchCount < 600:
            sleeptime = random.randint(2,10)
        # next fetch every 10-20 seconds
        else:
            sleeptime = random.randint(10,20)
        time.sleep(max(0,self.lastFetch+sleeptime-time.time()))
        self.fetchCount = self.fetchCount+1
        self.lastFetch  = time.time()


    def fetch(self, url, authenticate = False, data = None):
        """Fetch page"""
        if authenticate:
            cookies = self.GCparser.auth.getCookies()
            opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
        else:
            opener = urllib.request.build_opener()

        opener.addheaders = self.headers

        self.wait()
        self.log.debug("Fetching page '%s'." % url)
        if data is not None:
            web = opener.open(url, urllib.parse.urlencode(data))
        else:
            web = opener.open(url)

        if authenticate:
            self.GCparser.auth.saveCookies()

        return web



class Authenticator(object):
    def __init__(self, GCparser, username = None, password = None, dataDir = "~/.geocaching/parser"):
        self.log = logging.getLogger("GCparser.Auth")
        self.GCparser = GCparser

        self.username = username
        self.password = password
        if username is None or password is None:
            self.log.warning("No geocaching.com credentials given, some features will be disabled.")

        dataDir = os.path.expanduser(dataDir)
        if os.path.isdir(dataDir):
            self.dataDir = dataDir
            self.log.info("Setting data directory to '%s'." % dataDir)
        else:
            self.log.warn("Data directory '%s' does not exist, saving cookies will be disabled." % dataDir)
            self.dataDir = None

        self.cookies = None


    def cookieFileName(self):
        """Returns filename to store cookies"""
        return "%s/%s.cookie" % (self.dataDir, md5(self.username.encode("utf-8")).hexdigest())


    def loadCookies(self):
        """Try to load cookies, if possible"""
        if self.dataDir is None:
            self.log.debug("Cannot load cookies - invalid data directory.")
            self.cookies = CJ.CookieJar()
            return False
        elif os.path.exists(self.cookieFileName()):
            self.log.debug("Re-using stored cookies.")
            self.cookies = CJ.LWPCookieJar(self.cookieFileName())
            self.cookies.load(ignore_discard=True)
            logged = False
            for cookie in self.cookies:
                if cookie.name == "userid":
                    logged = True
            return logged
        else:
            self.log.debug("No stored cookies, creating new.")
            self.cookies = CJ.LWPCookieJar(self.cookieFileName())
            return False


    def saveCookies(self):
        """Try to save cookies, if possible"""
        if self.dataDir is not None:
            self.log.debug("Saving cookies.")
            self.cookies.save(ignore_discard=True, ignore_expires=True)


    def getCookies(self):
        """Returns login cookiejar"""

        # Already have cookies, let's return that
        if self.cookies is not None:
            return self.cookies

        # Don't have username => cannot proceed
        if self.username is None:
            self.log.critical("Username not available.")
            self.GCparser.die()

        # Let's try to load stored cookies from file
        if not self.loadCookies():
            self.login()

        return self.cookies


    def login(self):
        """Log in to geocaching.com, save cookiejar"""
        logged = self.loginAttempt()
        if not logged:
            self.log.debug("Not logged in, re-trying.")
            logged = self.loginAttempt()

        if not logged:
            self.log.critical("Login error.")
            self.GCparser.die()

        self.log.debug("Logged in.")
        self.saveCookies()


    def loginAttempt(self):
        """Try to log in to geocaching.com"""
        self.log.debug("Attempting to log in.")

        if self.username is None or self.password is None:
            self.log.critical("Cannot log in - no credentials available.")
            self.GCparser.die()

        webpage = self.GCparser.fetch.fetch("http://www.geocaching.com/", authenticate = True)

        data = {}
        data["ctl00$MiniProfile$loginUsername"] = self.username
        data["ctl00$MiniProfile$loginPassword"] = self.password
        data["ctl00$MiniProfile$LoginBtn"]      = "Go"
        data["ctl00$MiniProfile$loginRemember"] = "on"

        line = webpage.readline()
        while line:
            match = re.search('<input type="hidden" name="([^"]+)"[^>]+value="([^"]+)"', line.decode("utf-8"))
            if match:
                data[match.group(1)] = match.group(2)
            line = webpage.readline()

        webpage = self.GCparser.fetch.fetch("http://www.geocaching.com/Default.aspx", data = data, authenticate = True)

        logged = False
        for cookie in self.cookies:
            if cookie.name == "userid":
                logged = True

        return logged



"""
    PARSERS
"""

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
            self.details["guid"] = self.unescape(match.group(4))
            self.details["owner"] = self.unescape(match.group(5)).strip()
            self.details["owner_id"] = self.unescape(match.group(3))
            self.log.log(5, "guid = %s" % self.details["guid"])
            self.log.log(5, "type = %s" % self.details["type"])
            self.log.log(5, "owner = %s" % self.details["owner"])
            self.log.log(5, "owner_id = %s" % self.details["owner_id"])
        else:
            self.details["type"] = ""
            self.details["guid"] = ""
            self.details["owner"] = ""
            self.details["owner_id"] = ""
            self.log.error("Type, guid, owner, owner_id not found.")

        match = re.search("<img[^>]*src=['\"][^'\"]*/icons/container/[^'\"]*['\"][^>]*alt=['\"]Size: ([^'\"]+)['\"][^>]*>", self.data, re.I)
        if match:
            self.details["size"] = self.unescape(match.group(1)).strip()
            self.log.log(5, "size = %s" % self.details["size"])
        else:
            self.details["size"] = ""
            self.log.error("Size not found.")

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
            web = self.GCparser.fetch.fetch("http://www.geocaching.com/my/logs.aspx?s=1", authenticate=True)
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
            cache = None
            for line in self.data.splitlines():
                match = re.search("<td[^>]*><img[^>]*(Found it|Webcam Photo Taken|Attended)[^>]*></td>", line, re.I)
                if match:
                    cache = {"sequence":total-len(self.cacheList)}
                    self.log.debug("NEW cache record")
                    self.log.log(5, "sequence = %d" % cache["sequence"])

                if cache is not None:
                    if "f_date" not in cache:
                        match = re.search("<td[^>]*>([0-9]+)/([0-9]+)/([0-9]+)</td>", line, re.I)
                        if match:
                            cache["f_date"] = "%4d-%02d-%02d" % (int(match.group(3)), int(match.group(1)), int(match.group(2)))
                            self.log.log(5, "f_date = %s" % cache["f_date"])

                    if "guid" not in cache:
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
                        cache = None

        return self.cacheList


    def getCount(self):
        """returns total count of found logs"""
        if self.count is not None:
            return self.count

        self.load()

        self.count = len(re.findall("<td[^>]*><img[^>]*(Found it|Webcam Photo Taken|Attended)[^>]*></td>", self.data, re.I))

        return self.count



class EditProfile(BaseParser):
    def __init__(self, GCparser, profileData):
        BaseParser.__init__(self, GCparser)
        self.log = logging.getLogger("GCparser.ProfileEdit")
        self.profileData = profileData


    def getForm(self):
        """Prepare form for updating profile"""
        profile = self.GCparser.fetch.fetch("http://www.geocaching.com/account/editprofiledetails.aspx", authenticate=True)
        self.read(profile)
        if not self.checkLogin():
            self.GCparser.auth.login()
            self.getForm()


    def save(self):
        """Saves data in user's profile"""
        self.getForm()

        data = {}
        for line in self.data.splitlines():
            match = re.search('<input type="hidden" name="([^"]+)"[^>]+value="([^"]+)"', line)
            if match:
                data[match.group(1)] = match.group(2)
        data["ctl00$ContentBody$uxProfileDetails"] = self.profileData
        data["ctl00$ContentBody$uxSave"] = "Save Changes"

        profile = self.GCparser.fetch.fetch("http://www.geocaching.com/account/editprofiledetails.aspx", data = data, authenticate = True)
        self.read(profile)
