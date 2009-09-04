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
import time
import random

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