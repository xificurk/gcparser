# -*- coding: utf-8 -*-
"""
    GCparser.py - main classes of GCparser.
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

import logging, os, sys, time, random, urllib, re
from hashlib import md5
import http.cookiejar as CJ
import Parsers

class GCparser(object):
    def __init__(self, username = None, password = None, dataDir = "~/.geocaching/parser/"):
        self.log = logging.getLogger("GCparser")

        self.auth  = Authenticator(self, username, password, dataDir)
        self.fetch = Fetcher(self)

    def die(self):
        """Unrecoverable error, terminate application"""
        sys.exit()

    def myFinds(self):
        """Parse: My Profile > My Logs > Geocaches > Found it"""
        return Parsers.MyFinds(self)

    def cache(self, guid = None, waypoint = None, logs = None):
        """Parse: Cache details page"""
        return Parsers.Cache(self, guid = guid, waypoint = waypoint, logs = logs)



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
    def __init__(self, GCparser, username = None, password = None, dataDir = "~/.geocaching/parser/"):
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
        return self.dataDir + md5(self.username.encode("utf-8")).hexdigest() + ".cookie"


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
            match = re.search('<input type="hidden" name="([^"]+)"[^>]+value="([^"]+)"', line.decode('utf-8'))
            if match:
                data[match.group(1)] = match.group(2)
            line = webpage.readline()

        webpage = self.GCparser.fetch.fetch("http://www.geocaching.com/Default.aspx", data = data, authenticate = True)

        logged = False
        for cookie in self.cookies:
            if cookie.name == "userid":
                logged = True

        return logged

