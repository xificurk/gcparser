# -*- coding: utf-8 -*-
"""
    Authenticator.py - takes care of logging into geocaching.com.
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
import os
from hashlib import md5
import http.cookiejar as CJ
import re

class Authenticator(object):
    def __init__(self, GCparser, username = None, password = None, dataDir = "~/.geocaching/parser/"):
        self.log = logging.getLogger("GCparser.Auth")
        self.GCparser = GCparser

        self.username = username
        self.password = password
        if username is None or password is None:
            self.log.warning("No geocaching.com credentials given, some features will be disabled.")

        dataDir = os.path.expanduser(dataDir)
        if os.path.exists(dataDir):
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
