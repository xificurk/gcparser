# -*- coding: utf-8 -*-
"""
Parsing geocaching.com website.

Variables:
    parsers     --- Dictionary containing parser classes.

Classes:
    HTTPDatasource      --- Datasource retrieving data directly from
                            geocaching.com website.
    BaseParser          --- Define basic interface for Parser classes.
    CacheParser         --- Parse cache details.
    MyFindsParser       --- Parse myfinds list.
    SeekParser          --- Parse seek query.
    ProfileEdit         --- Profile edit.
    CredentialsError    --- Raised on invalid credentials.
    LoginError          --- Raised when geocaching.com login fails.
    DatasourceError     --- Raised on invalid datasource.

"""

__author__ = "Petr Morávek (xificurk@gmail.com)"
__copyright__ = "Copyright (C) 2009-2010 Petr Morávek"
__license__ = "GPL"

__version__ = "0.6.0"

from collections import UserDict, UserList
from datetime import date, datetime, timedelta
from hashlib import md5
from html.parser import HTMLParser
from http.cookiejar import CookieJar, LWPCookieJar
from logging import getLogger, addLevelName
import os.path
from random import randint
import re
from time import time, sleep
from unicodedata import normalize
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor

__all__ = ["parsers",
           "HTTPDatasource",
           "BaseParser",
           "CacheParser",
           "MyFindsParser",
           "SeekParser",
           "ProfileEdit",
           "CredentialsError",
           "LoginError",
           "DatasourceError"]


############################################################
### Datasources.                                         ###
############################################################

class HTTPDatasource:
    """
    Datasource retrieving data directly from geocaching.com website.

    Attributes:
        username    --- Geocaching.com username.
        password    --- Geocaching.com password.
        data_dir    --- Directory for storing cookies, user_agent, download
                        stats...
        stats       --- Dictionary with download stats of pages with auth=True.
        request_avg_time --- Desired average request sleep time for pages with
                             auth=True.

    Methods:
        request     --- Retrive data from geocaching.com website.
        wait        --- Called when downloading page with auth=True to lessen
                        the load on geocaching.com website.

    """

    request_avg_time = 600

    def __init__(self, username=None, password=None, data_dir="~/.geocaching/parser"):
        """
        Arguments:
            username    --- Geocaching.com username.
            password    --- Geocaching.com password.
            data_dir    --- Directory for storing cookies, user_agent, download
                            stats...

        """
        self._log = getLogger("gcparser.datasource.http")
        self.username = username
        self.password = password
        if username is None or password is None:
            self._log.warn("No geocaching.com credentials given, some features will be disabled.")
        data_dir = os.path.expanduser(data_dir)
        if os.path.isdir(data_dir):
            self.data_dir = data_dir
            self._log.debug("Setting data directory to '{0}'.".format(data_dir))
        else:
            self._log.warn("Data directory '{0}' does not exist, caching will be disabled.".format(data_dir))
            self.data_dir = None
        self._cookies = None
        self._user_agent = None
        self._load_stats()
        self._last_download = 0
        self._first_download = 0
        self._download_count = 0

    def request(self, url, auth=False, data=None, check=True):
        """
        Retrive data from geocaching.com website.

        Arguments:
            url         --- Webpage URL.

        Keyworded arguments:
            auth        --- Authenticate before request.
            data        --- Data to send with request.
            check       --- Re-check if we're logged in after download.

        """
        if auth:
            cookies = self._get_cookies()
            opener = build_opener(HTTPCookieProcessor(cookies))
        else:
            opener = build_opener()
        headers = []
        headers.append(("User-agent", self._get_user_agent()))
        headers.append(("Accept", "text/xml,application/xml,application/xhtml+xml,text/html;q=0.9,text/plain;q=0.8"))
        headers.append(("Accept-Language", "en-us,en;q=0.5"))
        headers.append(("Accept-Charset", "utf-8,*;q=0.5"))
        opener.addheaders = headers
        if auth:
            self.wait()
        else:
            sleep(max(0, self._last_download + 1 - time()))
            self._last_download = time()
        self._log.debug("Downloading page '{0}'.".format(url))
        webpage = self._download_webpage(opener, url, data)
        if auth:
            self._save_cookies()
            today = date.today().isoformat()
            if today not in self.stats:
                self.stats[today] = 0
            self.stats[today] += 1
            self._save_stats()
        webpage = webpage.read().decode("utf8")
        if auth and check and not self._check_login(webpage):
            self._log.debug("We're not actually logged in, refreshing login and redownloading page.")
            self._login()
            return self.request(url, auth=auth, data=data)
        return webpage

    def _download_webpage(self, opener, url, data, retry=1):
        """ Download the page. """
        try:
            if data is not None:
                webpage = opener.open(url, urlencode(data))
            else:
                webpage = opener.open(url)
        except IOError:
            self._log.error("An error occured while downloading '{0}', will retry in {1} seconds.".format(url, retry))
            sleep(retry)
            retry = min(5*retry, 600)
            return self._download_webpage(opener, url, data, retry=retry)
        return webpage

    def _user_file_name(self):
        """ Returns filename to store user's data. """
        if self.username is None or self.data_dir is None:
            return None
        hash_ = md5(self.username.encode("utf8")).hexdigest()
        name = normalize("NFKD", self.username).encode("ascii", "ignore").decode("ascii")
        name = _pcre("file_mask").sub("", name)
        name = name + "_" + hash_
        return os.path.join(self.data_dir, name)

    def _get_cookies(self):
        """ Get cookies - load from file, or create. """
        if self._cookies is not None:
            return self._cookies
        user_file = self._user_file_name()
        if user_file is None:
            self._log.debug("Cannot load cookies - invalid filename.")
            self._cookies = CookieJar()
            self._login()
        else:
            cookie_file = user_file + ".cookie"
            if os.path.isfile(cookie_file):
                self._log.debug("Re-using stored cookies.")
                self._cookies = LWPCookieJar(cookie_file)
                self._cookies.load(ignore_discard=True)
                logged = False
                for cookie in self._cookies:
                    if cookie.name == "userid":
                        logged = True
                        break
                if not logged:
                    self._login()
            else:
                self._log.debug("No stored cookies, creating new.")
                self._cookies = LWPCookieJar(cookie_file)
                self._login()
        return self._cookies

    def _save_cookies(self):
        """ Try to save cookies, if possible. """
        if isinstance(self._cookies, LWPCookieJar):
            self._log.debug("Saving cookies.")
            self._cookies.save(ignore_discard=True, ignore_expires=True)

    def _get_user_agent(self):
        """ Return current user_agent, or load from file, or generate random one. """
        if self._user_agent is not None:
            return self._user_agent
        user_file = self._user_file_name()
        if user_file is None:
            self._user_agent = self._generate_user_agent()
        else:
            ua_file = user_file + ".ua"
            if os.path.isfile(ua_file):
                with open(ua_file, "r", encoding="utf8") as fp:
                    self._log.debug("Loading user agent.")
                    self._user_agent = fp.read()
            else:
                self._user_agent = self._generate_user_agent()
                self._save_user_agent()
        return self._user_agent

    def _save_user_agent(self):
        """ Try to save user agent, if possible. """
        if self._user_agent is None:
            return
        user_file = self._user_file_name()
        if user_file is None:
            return
        ua_file = user_file + ".ua"
        with open(ua_file, "w", encoding="utf8") as fp:
            self._log.debug("Saving user agent.")
            fp.write(self._user_agent)

    def _generate_user_agent(self):
        """ Generate random user_agent string - masking as Firefox 3.0.x. """
        self._log.debug("Generating user agent.")
        system = randint(1, 5)
        if system <= 1:
            system = "X11"
            system_version = ["Linux i686", "Linux x86_64"]
        elif system <= 2:
            system = "Macintosh"
            system_version = ["PPC Mac OS X 10.5"]
        else:
            system = "Windows"
            system_version = ["Windows NT 5.1", "Windows NT 6.0", "Windows NT 6.1"]
        system_version = system_version[randint(0, len(system_version) - 1)]
        version = randint(1, 13)
        date = "200907{0:02d}{1:02d}".format(randint(1, 31), randint(1, 23))
        return "Mozilla/5.0 ({0}; U; {1}; en-US; rv:1.9.0.{2:d}) Gecko/{3} Firefox/3.0.{2:d}".format(system, system_version, version, date)

    def _load_stats(self):
        """ Load download stats from file. """
        user_file = self._user_file_name()
        if user_file is None:
            return
        self.stats = {}
        stats_file = user_file + ".stats"
        if os.path.isfile(stats_file):
            today = date.today()
            timeout = today - timedelta(days=93)
            with open(stats_file, "r", encoding="utf8") as fp:
                self._log.debug("Loading stats.")
                for line in fp.readlines():
                    line = line.strip()
                    if not line:
                        continue
                    line = line.split("\t")
                    download_date = line[0].split("-")
                    download_date = date(int(download_date[0]), int(download_date[1]), int(download_date[2]))
                    download_count = int(line[1])
                    if download_date > timeout:
                        self.stats[download_date.isoformat()] = download_count

    def _save_stats(self):
        """ Try to save stats, if possible. """
        user_file = self._user_file_name()
        if user_file is None:
            return
        stats_file = user_file + ".stats"
        with open(stats_file, "w", encoding="utf8") as fp:
            self._log.debug("Saving stats.")
            for download_date, download_count in self.stats.items():
                fp.write("{0}\t{1}".format(download_date, download_count))

    def _login(self):
        """ Log in to geocaching.com, save cookiejar. """
        if not self._login_attempt():
            self._log.debug("Not logged in, re-trying.")
            if not self._login_attempt():
                self._log.critical("Login error.")
                raise LoginError
        self._log.debug("Logged in.")

    def _login_attempt(self):
        """ Attempt to log in to geocaching.com. """
        self._log.debug("Attempting to log in.")
        if self.username is None or self.password is None:
            self._log.critical("Cannot log in - no credentials available.")
            raise CredentialsError
        webpage = self.request("http://www.geocaching.com/", auth=True, check=False)
        data = {}
        data["ctl00$MiniProfile$loginUsername"] = self.username
        data["ctl00$MiniProfile$loginPassword"] = self.password
        data["ctl00$MiniProfile$LoginBtn"] = "Go"
        data["ctl00$MiniProfile$uxRememberMe"] = "on"
        for hidden_input in _pcre("hidden_input").findall(webpage):
            data[hidden_input[0]] = hidden_input[1]
        webpage = self.request("http://www.geocaching.com/Default.aspx", data=data, auth=True, check=False)
        for cookie in self._cookies:
            self._log.debug("{0}: {1}".format(cookie.name, cookie.value))
            if cookie.name == "userid":
                return True
        return False

    def _check_login(self, data):
        """ Checks the downloaded data and determines if we're logged in. """
        self._log.debug("Checking if we're really logged in...")
        if data is not None:
            for line in data.splitlines():
                if line.find("Sorry, the owner of this listing has made it viewable to Premium Members only") != -1:
                    self._log.debug("PM only cache.")
                    return True
                if line.find("You are not logged in.") != -1:
                    return False
        return True

    def wait(self):
        """
        Called when downloading page with auth=True to lessen the load on
        geocaching.com website.

        """
        # No request for a long time => reset _first_download value using desired average.
        self._first_download = max(time() - self._download_count * self.request_avg_time, self._first_download)
        # Calculate count
        count = self._download_count - int((time() - self._first_download) / self.request_avg_time)
        # sleep time 1s: 10/10s => overall 10/10s
        if count < 10:
            sleep_time = 1
        # sleep time 2-8s: 40/3.3m => overall 50/3.5min
        elif count < 50:
            sleep_time = randint(2, 8)
        # sleep time 5-35s: 155/51.6m => overall 205/55.1min
        elif count < 200:
            sleep_time = randint(5, 35)
        # sleep time 10-50s: 315/2.6h => overall 520/3.5h
        elif count < 500:
            sleep_time = randint(10, 50)
        # sleep time 20-80s
        else:
            sleep_time = randint(20, 80)
        sleep(max(0, self._last_download + sleep_time - time()))
        self._download_count = self._download_count + 1
        self._last_download = time()



############################################################
### Helpers.                                             ###
############################################################

_months_abbr = {"Jan":1, "Feb":2, "Mar":3, "Apr":4, "May":5, "Jun":6, "Jul":7, "Aug":8, "Sep":9, "Oct":10, "Nov":11, "Dec":12}
_months_full = {"January":1, "February":2, "March":3, "April":4, "May":5, "June":6, "July":7, "August":8, "September":9, "October":10, "November":11, "December":12}
_cache_types = {}
_cache_types["2"] = "Traditional Cache"
_cache_types["3"] = "Multi-cache"
_cache_types["8"] = "Mystery/Puzzle Cache"
_cache_types["5"] = "Letterbox Hybrid"
_cache_types["earthcache"] = "Earthcache"
_cache_types["1858"] = "Wherigo Cache"
_cache_types["6"] = "Event Cache"
_cache_types["4"] = "Virtual Cache"
_cache_types["11"] = "Webcam Cache"
_cache_types["13"] = "Cache In Trash Out Event"
_cache_types["mega"] = "Mega-Event Cache"
_cache_types["3653"] = "Lost and Found Event Cache"

def _clean_HTML(text):
    """ Cleans text from HTML markup and unescapes entities. """
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = _pcre("HTMLp").sub("\n** ", text)
    text = _pcre("HTMLbr").sub("\n", text)
    text = _pcre("HTMLli").sub("\n - ", text)
    text = _pcre("HTMLh").sub("\n", text)
    text = _pcre("HTMLimg_wink").sub(" ;-) ", text)
    text = _pcre("HTMLimg_smile_big").sub(" :D ", text)
    text = _pcre("HTMLimg_smile").sub(" :-) ", text)
    text = _pcre("HTMLimgalt").sub("[img \\1]", text)
    text = _pcre("HTMLimg").sub("[img]", text)
    text = _pcre("HTMLtag").sub("", text)
    # Escape entities
    text = _unescape(text)
    # Remove unnecessary spaces
    text = _pcre("blank_line").sub("", text)
    text = _pcre("double_space").sub(" ", text)
    return text

_unescape = HTMLParser().unescape

_pcres = {}
_pcre_masks = {}

def _pcre(name):
    """ Return compiled PCRE. """
    if name not in _pcre_masks:
        getLogger("gcparser.helpers").error("Uknown PCRE '{0}'.".format(name))
        name = "null"
    if name not in _pcres:
        _pcres[name] = re.compile(_pcre_masks[name][0], _pcre_masks[name][1])
    return _pcres[name]

########################################
# PCRE: System.                        #
########################################
_pcre_masks["null"] = (".*", 0)
_pcre_masks["file_mask"] = ("[^a-zA-Z0-9._-]+", re.A)

########################################
# PCRE: System.                        #
########################################
_pcre_masks["HTMLp"] = ("<p[^>]*>", re.I)
_pcre_masks["HTMLbr"] = ("<br[^>]*>", re.I)
_pcre_masks["HTMLli"] = ("<li[^>]*>", re.I)
_pcre_masks["HTMLh"] = ("</?h[0-9][^>]*>", re.I)
_pcre_masks["HTMLimg_wink"] = ("<img\s+src=\s*['\"]http://www\.geocaching\.com/images/icons/icon_smile_wink\.gif['\"][^>]*>", re.I)
_pcre_masks["HTMLimg_smile"] = ("<img\s+src=\s*['\"]http://www\.geocaching\.com/images/icons/icon_smile\.gif['\"][^>]*>", re.I)
_pcre_masks["HTMLimg_smile_big"] = ("<img\s+src=\s*['\"]http://www\.geocaching\.com/images/icons/icon_smile_big\.gif['\"][^>]*>", re.I)
_pcre_masks["HTMLimgalt"] = ("<img[^>]*alt=['\"]([^'\"]+)['\"][^>]*>", re.I)
_pcre_masks["HTMLimg"] = ("<img[^>]*>", re.I)
_pcre_masks["HTMLtag"] = ("<[^>]*>", re.I)
_pcre_masks["blank_line"] = ("^\s+|\s+$|^\s*$\n", re.M)
_pcre_masks["double_space"] = ("\s\s+", 0)



############################################################
### Parsers.                                             ###
############################################################

LOG_PARSER = 5
addLevelName(LOG_PARSER, "PARSER")

########################################
# BaseParser.                          #
########################################
_pcre_masks["hidden_input"] = ("<input type=[\"']hidden[\"'] name=\"([^\"]+)\"[^>]+value=\"([^\"]*)\"", re.I)
_pcre_masks["guid"] = ("^[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+$", re.I)


class BaseParser:
    """
    Define basic interface for Parser classes.

    Attributes:
        datasource  --- Datasource instance.

    """

    datasource = None

    def __init__(self, datasource=None):
        """
        Keyworded arguments:
            datasource  --- Datasource instance, or None.

        """
        if datasource is not None:
            self.datasource = datasource
        self._log.debug("Using datasource {0}.".format(self.datasource))
        self._data = None
        if hasattr(self, "_log"):
            self._log.log_parser = lambda x: self._log.log(LOG_PARSER, x)

    def _load(self, url, auth=False, data=None):
        """ Loads data from webpage. """
        if self.datasource is None:
            raise DatasourceError()
        if self._data is None:
            self._data = self.datasource.request(url, auth=auth, data=data)

########################################
# CacheParser                          #
########################################
_pcre_masks["waypoint"] = ("GC[A-Z0-9]+", 0)
# The owner of <strong>The first Czech premium member cache</strong> has chosen to make this cache listing visible to Premium Members only.
_pcre_masks["PMonly"] = ("<img [^>]*alt=['\"]Premium Members only['\"][^>]*/>\s*The owner of <strong>\s*([^<]+)\s*</strong> has chosen to make this cache listing visible to Premium Members only.", re.I)
# <span id="ctl00_ContentBody_uxCacheType">A cache by Pc-romeo</span>
_pcre_masks["PMowner"] = ("<span[^>]*>\s*A cache by ([^<]+)\s*</span>", re.I)
# <img src="/images/icons/container/regular.gif" alt="Size: Regular" />&nbsp<small>(Regular)</small>
_pcre_masks["PMsize"] = ("\s*<img [^>]*alt=['\"]Size: ([^'\"]+)['\"][^>]*/>", re.I)
# <strong><span id="ctl00_ContentBody_lblDifficulty">Difficulty:</span></strong>
# <img src="http://www.geocaching.com/images/stars/stars1.gif" alt="1 out of 5" />
_pcre_masks["PMdifficulty"] = ("<strong><span[^>]*>Difficulty:</span></strong>\s*<img [^>]*alt=['\"]([0-9.]+) out of 5['\"][^>]*/>", re.I)
# <strong><span id="ctl00_ContentBody_lblTerrain">Terrain:</span></strong>
# <img src="http://www.geocaching.com/images/stars/stars1_5.gif" alt="1.5 out of 5" />
_pcre_masks["PMterrain"] = ("<strong><span[^>]*>Terrain:</span></strong>\s*<img [^>]*alt=['\"]([0-9.]+) out of 5['\"][^>]*/>", re.I)
# <img id="ctl00_ContentBody_uxWptTypeImage" src="http://www.geocaching.com/images/wpttypes/2.gif" style="border-width:0px;vertical-align:middle" />
_pcre_masks["PMcache_type"] = ("<img id=['\"]ctl00_ContentBody_uxWptTypeImage['\"] src=['\"][^'\"]*/images/wpttypes/(earthcache|mega|[0-9]+).gif['\"][^>]*>", re.I)
# <meta name="description" content="Pendulum - Prague Travel Bug Hotel (GCHCE0) was created by Saman on 12/23/2003. It&#39;s a Regular size geocache, with difficulty of 2, terrain of 2.5. It&#39;s located in Hlavni mesto Praha, Czech Republic. Literary - kinetic cache with the superb view of the Praguepanorama. A suitable place for the incoming and outgoing travelbugs." />
_pcre_masks["cache_details"] = ("<meta\s+name=\"description\" content=\"([^\"]+) \(GC[A-Z0-9]+\) was created by ([^\"]+) on ([0-9]+)/([0-9]+)/([0-9]+)\. It('|(&#39;))s a ([a-zA-Z ]+) size geocache, with difficulty of ([0-9.]+), terrain of ([0-9.]+). It('|(&#39;))s located in (([^,.]+), )?([^.]+)\.[^\"]*\"[^>]*>", re.I|re.S)
# <a href="/about/cache_types.aspx" target="_blank" title="About Cache Types"><img src="/images/WptTypes/8.gif" alt="Unknown Cache" width="32" height="32" />
_pcre_masks["cache_type"] = ("<img src=['\"]/images/WptTypes/[^'\"]+['\"] alt=\"([^\"]+)\"[^>]*></a>", re.I)
# by <a href="http://www.geocaching.com/profile/?guid=ed7a2040-3bbb-485b-9b03-21ae8507d2d7&wid=92322d1b-d354-4190-980e-8964d7740161&ds=2">
_pcre_masks["cache_owner_id"] = ("by <a href=['\"]http://www\.geocaching\.com/profile/\?guid=([a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+)&wid=([a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+)&ds=2['\"][^>]*>", re.I)
# <p class="OldWarning"><strong>Cache Issues:</strong></p><ul class="OldWarning"><li>This cache is temporarily unavailable. Read the logs below to read the status for this cache.</li></ul></span>
_pcre_masks["disabled"] = ("<p class=['\"]OldWarning['\"][^>]*><strong>Cache Issues:</strong></p><ul[^>]*><li>This cache (has been archived|is temporarily unavailable)[^<]*</li>", re.I)
# <span id="ctl00_ContentBody_LatLon" style="font-weight:bold;">N 50° 02.173 E 015° 46.386</span>
_pcre_masks["cache_coords"] = ("<span id=['\"]ctl00_ContentBody_LatLon['\"][^>]*>([NS]) ([0-9]+)° ([0-9.]+) ([WE]) ([0-9]+)° ([0-9.]+)</span>", re.I)
_pcre_masks["cache_shortDesc"] = ("<div class=['\"]UserSuppliedContent['\"]>\s*<span id=['\"]ctl00_ContentBody_ShortDescription['\"]>(.*?)</span>\s+</div>", re.I|re.S)
_pcre_masks["cache_longDesc"] = ("<div class=['\"]UserSuppliedContent['\"]>\s*<span id=['\"]ctl00_ContentBody_LongDescription['\"]>(.*?)</span>\s*</div>\s*<p>\s+</p>\s+</td>", re.I|re.S)
"""
<div id="div_hint" class="HalfLeft">
                Hint text
</div>
"""
_pcre_masks["cache_hint"] = ("<div id=['\"]div_hint['\"][^>]*>\s*(.*?)\s*</div>", re.I)
"""
<div class="CacheDetailNavigationWidget Spacing">
    <img src="/images/attributes/wheelchair-no.gif" alt="not wheelchair accessible" title="not wheelchair accessible" width="30" height="30" /> <img src="/images/attributes/firstaid-yes.gif" alt="needs maintenance" title="needs maintenance" width="30" height="30" /> <img src="/images/attributes/stealth-yes.gif" alt="stealth required" title="stealth required" width="30" height="30" /> <img src="/images/attributes/available-yes.gif" alt="available 24-7" title="available 24-7" width="30" height="30" /> <img src="/images/attributes/scenic-yes.gif" alt="scenic view" title="scenic view" width="30" height="30" /> <img src="/images/attributes/onehour-yes.gif" alt="takes less than 1  hour" title="takes less than 1  hour" width="30" height="30" /> <img src="/images/attributes/kids-yes.gif" alt="kid friendly" title="kid friendly" width="30" height="30" /> <img src="/images/attributes/dogs-yes.gif" alt="dogs allowed" title="dogs allowed" width="30" height="30" /> <img src="/images/attributes/attribute-blank.gif" alt="blank" title="blank" width="30" height="30" /> <img src="/images/attributes/attribute-blank.gif" alt="blank" title="blank" width="30" height="30" /> <img src="/images/attributes/attribute-blank.gif" alt="blank" title="blank" width="30" height="30" /> <img src="/images/attributes/attribute-blank.gif" alt="blank" title="blank" width="30" height="30" /> <p class="NoSpacing"><small><a href="/about/icons.aspx" title="What are Attributes?">What are Attributes?</a></small></p>
</div>
"""
_pcre_masks["cache_attributes"] = ("<div class=\"CacheDetailNavigationWidget Spacing\">\s*(.*?)\s*<p[^>]*><small><a href=['\"]/about/icons\.aspx['\"] title=['\"]What are Attributes\?['\"]>What are Attributes\?</a></small></p>\s*</div>", re.I|re.S)
_pcre_masks["cache_attributes_item"] = ("title=\"([^\"]+)\"", re.I)
"""
    <span id="ctl00_ContentBody_uxTravelBugList_uxInventoryLabel">Inventory</span>
</h3>
<div class="WidgetBody">
    <ul>
    <li>
        <a href="http://www.geocaching.com/track/details.aspx?guid=0eac9e5f-dc6c-4ec3-b1b7-4663245982ef" class="lnk">
            <img src="http://www.geocaching.com/images/wpttypes/sm/21.gif" width="16" /><span>Bob the Bug</span></a>
    </li>
    <li>

        <a href="http://www.geocaching.com/track/details.aspx?guid=0511b8eb-ddaa-4484-9a38-a2d8b3b6a77b" class="lnk">
            <img src="http://www.geocaching.com/images/wpttypes/sm/1998.gif" width="16" /><span>Barusky trsatko ;-)</span></a>
    </li>
    <li>
        <a href="http://www.geocaching.com/track/details.aspx?guid=b82c9582-3d66-425a-91e1-c99f1e3e88d9" class="lnk">
            <img src="http://www.geocaching.com/images/wpttypes/sm/2059.gif" width="16" /><span>Travel Ingot Mr. East</span></a>
    </li>
    </ul>
"""
_pcre_masks["cache_inventory"] = ("<span\s+id=\"ctl00_ContentBody_uxTravelBugList_uxInventoryLabel\">Inventory</span>\s*</h3>\s*<div[^>]*>\s*<ul[^>]*>(.*?)</ul>", re.I|re.S)
"""
<a href="http://www.geocaching.com/track/details.aspx?guid=b82c9582-3d66-425a-91e1-c99f1e3e88d9" class="lnk">
    <img src="http://www.geocaching.com/images/wpttypes/sm/2059.gif" width="16" /><span>Travel Ingot Mr. East</span></a>
"""
_pcre_masks["cache_inventory_item"] = ("<a href=['\"][^'\"]*/track/details\.aspx\?guid=([a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+-[a-z0-9]+)['\"][^>]*>\s*<img[^>]*>\s*<span>([^<]+)</span></a>", re.I)
# <span id="ctl00_ContentBody_lblFindCounts"><p><img src="/images/icons/icon_smile.gif" alt="Found it" />113&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="/images/icons/icon_note.gif" alt="Write note" />19&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="/images/icons/icon_remove.gif" alt="Needs Archived" />1&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="/images/icons/icon_disabled.gif" alt="Temporarily Disable Listing" />2&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="/images/icons/icon_enabled.gif" alt="Enable Listing" />1&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="/images/icons/icon_greenlight.gif" alt="Publish Listing" />1&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="/images/icons/icon_maint.gif" alt="Owner Maintenance" />2&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<img src="/images/icons/big_smile.gif" alt="Post Reviewer Note" />3&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</p></span>
_pcre_masks["cache_visits"] = ("<span id=['\"]ctl00_ContentBody_lblFindCounts['\"][^>]*><p[^>]*>(.*?)</p></span>", re.I)
# <img src="/images/icons/icon_smile.gif" alt="Found it" />113
_pcre_masks["cache_log_count"] = ("<img[^>]*alt=\"([^\"]+)\"[^>]*/>([0-9]+)", re.I)
_pcre_masks["cache_logs"] = ("<table class=\"LogsTable Table\">(.*?)</table>\s", re.I)
_pcre_masks["cache_log"] = ("<tr><td[^>]*><strong><img.*?title=['\"]([^\"']+)['\"][^>]*/>&nbsp;([a-z]+) ([0-9]+)(, ([0-9]+))? by <a[^>]*>([^<]+)</a></strong>(&nbsp;| )\([0-9]+ found\)<br\s*/><br\s*/>(.*?)<br\s*/><br\s*/><small><a href=['\"]log.aspx\?LUID=[^\"]+['\"] title=['\"]View Log['\"]>View Log</a></small>", re.I)


class CacheParser(BaseParser, UserDict):
    """
    Parse cache details.

    Subclass of UserDict.

    Attributes:
        details     --- Dictionary with cache details.

    Methods:
        get_details --- Parse and return cache details.

    """

    def __init__(self, id_, logs=False, datasource=None):
        """
        Arguments:
            id_         --- Geocache waypoint or guid.

        Keyworded arguments:
            logs        --- Download complete list of logs.
            datasource  --- Datasource instance, or None.

        """
        self._log = getLogger("gcparser.parser.cache")
        BaseParser.__init__(self, datasource=datasource)
        self._id = id_
        if _pcre("guid").match(id_) is not None:
            self._type = "guid"
        else:
            self._type = "waypoint"
        self._url = "http://www.geocaching.com/seek/cache_details.aspx?decrypt=y"
        if self._type == "guid":
            self._url = self._url + "&guid=" + self._id
        else:
            self._url = self._url + "&wp=" + self._id
        if logs:
            self._url = self._url + "&log=y"
        self._details = None

    def _load(self):
        """ Loads data from webpage. """
        BaseParser._load(self, self._url, auth=True)

    @property
    def data(self):
        return self.details

    @property
    def details(self):
        """ Dictionary with cache details. """
        if self._details is None:
            self._details = self.get_details()
        return self._details

    def get_details(self):
        """
        Parse and return cache details.

        """
        self._load()
        details = {}
        if self._type == "guid":
            details["guid"] = self._id
        else:
            details["waypoint"] = self._id

        match = _pcre("waypoint").search(self._data)
        if match is not None:
            details["waypoint"] = match.group(0)
            self._log.log_parser("waypoint = {0}".format(details["waypoint"]))
        else:
            details["waypoint"] = ""
            self._log.error("Waypoint not found.")

        match = _pcre("PMonly").search(self._data)
        if match is not None:
            details["PMonly"] = True
            self._log.warn("PM only cache at '{0}'.".format(self._url))

            details["name"] = _unescape(match.group(1)).strip()
            self._log.log_parser("name = {0}".format(details["name"]))

            match = _pcre("PMowner").search(self._data)
            if match is not None:
                details["owner"] = _unescape(match.group(1)).strip()
                self._log.log_parser("owner = {0}".format(details["owner"]))
            else:
                details["owner"] = ""
                self._log.error("Could not parse cache owner.")

            match = _pcre("PMsize").search(self._data)
            if match is not None:
                details["size"] = match.group(1).strip()
                self._log.log_parser("size = {0}".format(details["size"]))
            else:
                details["size"] = ""
                self._log.error("Could not parse cache size.")

            match = _pcre("PMdifficulty").search(self._data)
            if match is not None:
                details["difficulty"] = float(match.group(1))
                self._log.log_parser("difficulty = {0:.1f}".format(details["difficulty"]))
            else:
                details["difficulty"] = 0
                self._log.error("Could not parse cache difficulty.")

            match = _pcre("PMterrain").search(self._data)
            if match is not None:
                details["terrain"] = float(match.group(1))
                self._log.log_parser("terrain = {0:.1f}".format(details["terrain"]))
            else:
                details["terrain"] = 0
                self._log.error("Could not parse cache terrain.")

            match = _pcre("PMcache_type").search(self._data)
            if match is not None and match.group(1) in _cache_types:
                details["type"] = _cache_types[match.group(1)]
                self._log.log_parser("type = {0}".format(details["type"]))
            else:
                details["type"] = ""
                self._log.error("Type not found.")
        else:
            details["PMonly"] = False

            match = _pcre("cache_details").search(self._data)
            if match is not None:
                details["name"] = _unescape(_unescape(match.group(1))).strip()
                details["owner"] = _unescape(_unescape(match.group(2))).strip()
                details["hidden"] = "{0:04d}-{1:02d}-{2:02d}".format(int(match.group(5)), int(match.group(3)), int(match.group(4)))
                details["size"] = match.group(8).strip()
                details["difficulty"] = float(match.group(9))
                details["terrain"] = float(match.group(10))
                if match.group(14) is not None:
                    details["province"] = _unescape(match.group(14)).strip()
                else:
                    details["province"] = ""
                details["country"] = _unescape(match.group(15)).strip()
                self._log.log_parser("name = {0}".format(details["name"]))
                self._log.log_parser("owner = {0}".format(details["owner"]))
                self._log.log_parser("hidden = {0}".format(details["hidden"]))
                self._log.log_parser("size = {0}".format(details["size"]))
                self._log.log_parser("difficulty = {0:.1f}".format(details["difficulty"]))
                self._log.log_parser("terrain = {0:.1f}".format(details["terrain"]))
                self._log.log_parser("country = {0}".format(details["country"]))
                self._log.log_parser("province = {0}".format(details["province"]))
            else:
                details["name"] = ""
                details["owner"] = ""
                details["hidden"] = "1980-01-01"
                details["size"] = ""
                details["difficulty"] = 0
                details["terrain"] = 0
                self._log.error("Could not parse cache details.")

            match = _pcre("cache_type").search(self._data)
            if match is not None:
                details["type"] = _unescape(match.group(1)).strip()
                # GS weird changes bug
                if details["type"] == "Unknown Cache":
                    details["type"] = "Mystery/Puzzle Cache"
                self._log.log_parser("type = {0}".format(details["type"]))
            else:
                details["type"] = ""
                self._log.error("Type not found.")

            match = _pcre("cache_owner_id").search(self._data)
            if match is not None:
                details["owner_id"] = match.group(1)
                details["guid"] = match.group(2)
                self._log.log_parser("guid = {0}".format(details["guid"]))
                self._log.log_parser("owner_id = {0}".format(details["owner_id"]))
            else:
                details["owner_id"] = ""
                self._log.error("Owner id not found.")
                if "guid" not in details:
                    details["guid"] = ""
                    self._log.error("Guid not found.")

            details["disabled"] = 0
            details["archived"] = 0
            match = _pcre("disabled").search(self._data)
            if match is not None:
                if match.group(1) == "has been archived":
                    details["archived"] = 1
                details["disabled"] = 1
                self._log.log_parser("archived = {0}".format(details["archived"]))
                self._log.log_parser("disabled = {0}".format(details["disabled"]))

            match = _pcre("cache_coords").search(self._data)
            if match is not None:
                details["lat"] = float(match.group(2)) + float(match.group(3))/60
                if match.group(1) == "S":
                    details["lat"] = -details["lat"]
                details["lon"] = float(match.group(5)) + float(match.group(6))/60
                if match.group(4) == "W":
                    details["lon"] = -details["lon"]
                self._log.log_parser("lat = {0:.5f}".format(details["lat"]))
                self._log.log_parser("lon = {0:.5f}".format(details["lon"]))
            else:
                details["lat"] = 0
                details["lon"] = 0
                self._log.error("Lat, lon not found.")

            match = _pcre("cache_shortDesc").search(self._data)
            if match is not None:
                details["shortDescHTML"] = match.group(1)
                details["shortDesc"] = _clean_HTML(match.group(1))
                self._log.log_parser("shortDesc = {0}...".format(details["shortDesc"].replace("\n"," ")[0:50]))
            else:
                details["shortDescHTML"] = ""
                details["shortDesc"] = ""

            match = _pcre("cache_longDesc").search(self._data)
            if match is not None:
                details["longDescHTML"] = match.group(1)
                details["longDesc"] = _clean_HTML(match.group(1))
                self._log.log_parser("longDesc = {0}...".format(details["longDesc"].replace("\n"," ")[0:50]))
            else:
                details["longDescHTML"] = ""
                details["longDesc"] = ""

            match = _pcre("cache_hint").search(self._data)
            if match is not None:
                details["hint"] = _unescape(match.group(1).replace("<br>", "\n")).strip()
                self._log.log_parser("hint = {0}...".format(details["hint"].replace("\n"," ")[0:50]))
            else:
                details["hint"] = ""

            match = _pcre("cache_attributes").search(self._data)
            if match is not None:
                details["attributes"] = []
                for item in _pcre("cache_attributes_item").finditer(match.group(1)):
                    attr = _unescape(item.group(1)).strip()
                    if attr != "blank":
                        details["attributes"].append(attr)
                details["attributes"] = ", ".join(details["attributes"])
                self._log.log_parser("attributes = {0}".format(details["attributes"]))
            else:
                details["attributes"] = ""

            details["inventory"] = {}
            match = _pcre("cache_inventory").search(self._data)
            if match is not None:
                for part in match.group(1).split("</li>"):
                    match = _pcre("cache_inventory_item").search(part)
                    if match is not None:
                        details["inventory"][match.group(1)] = _unescape(match.group(2)).strip()
                self._log.log_parser("inventory = {0}".format(details["inventory"]))

            details["visits"] = {}
            match = _pcre("cache_visits").search(self._data)
            if match is not None:
                for part in match.group(1).split("&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"):
                    match = _pcre("cache_log_count").search(part)
                    if match is not None:
                        details["visits"][_unescape(match.group(1)).strip()] = int(match.group(2))
                self._log.log_parser("visits = {0}".format(details["visits"]))

            details["logs"] = []
            match = _pcre("cache_logs").search(self._data)
            if match is not None:
                for part in match.group(1).split("</tr>"):
                    match = _pcre("cache_log").match(part)
                    if match is not None:
                        if match.group(5) is not None:
                            year = match.group(5)
                        else:
                            year = datetime.now().year
                        log_date = "{0:04d}-{1:02d}-{2:02d}".format(int(year), int(_months_full[match.group(2)]), int(match.group(3)))
                        details["logs"].append((match.group(1), log_date, match.group(6), match.group(8)))
                self._log.log_parser("Found {0} logs.".format(len(details["logs"])))

        return details



########################################
# MyFindsParser                        #
########################################
# <img src="/images/icons/icon_smile.gif" width="16" height="16" alt="Found it" />
_pcre_masks["logs_found"] = ("\s*<img[^>]*(Found it|Webcam Photo Taken|Attended)[^>]*>", re.I)
# 7/23/2008
_pcre_masks["logs_date"] = ("\s*([0-9]+)/([0-9]+)/([0-9]+)", re.I)
# <a href="http://www.geocaching.com/seek/cache_details.aspx?guid=331f0c62-ef78-4ab3-b8d7-be569246771d" class="ImageLink"><img src="http://www.geocaching.com/images/wpttypes/sm/2.gif" title="Traditional Cache" /></a> <a href="http://www.geocaching.com/seek/cache_details.aspx?guid=331f0c62-ef78-4ab3-b8d7-be569246771d">Stepankovi hrosi</a>&nbsp;
# <a href="http://www.geocaching.com/seek/cache_details.aspx?guid=d3e80a41-4218-4136-bb63-ac0de3ef0b5a" class="ImageLink"><img src="http://www.geocaching.com/images/wpttypes/sm/8.gif" title="Unknown Cache" /></a> <a href="http://www.geocaching.com/seek/cache_details.aspx?guid=d3e80a41-4218-4136-bb63-ac0de3ef0b5a"><span class="Strike">Barva Kouzel</span></a>&nbsp;
# <a href="http://www.geocaching.com/seek/cache_details.aspx?guid=29444383-4607-4e2d-bc65-bcf2e9919e5d" class="ImageLink"><img src="http://www.geocaching.com/images/wpttypes/sm/2.gif" title="Traditional Cache" /></a> <a href="http://www.geocaching.com/seek/cache_details.aspx?guid=29444383-4607-4e2d-bc65-bcf2e9919e5d"><span class="Strike OldWarning">Krizovatka na kopci / Crossroad on a hill</span></a>&nbsp;
_pcre_masks["logs_name"] = ("\s*<a[^>]*>\s*<img[^>]*>\s*</a>\s*<a href=['\"][^'\"]*/seek/cache_details.aspx\?guid=([a-z0-9-]+)['\"][^>]*>\s*(<span class=['\"]Strike(\s*OldWarning)?['\"]>)?\s*([^<]+)\s*(</span>)?\s*</a>", re.I)
# <a href="http://www.geocaching.com/seek/log.aspx?LUID=a3e234b3-7d34-4a26-bde5-487e4297133c" target="_blank" title="Visit Log">Visit Log</a>
_pcre_masks["logs_log"] = ("\s*<a href=['\"][^'\"]*/seek/log.aspx\?LUID=([a-z0-9-]+)['\"][^>]*>Visit Log</a>", re.I)


class MyFindsParser(BaseParser, UserList):
    """
    Parse myfinds list.

    Subclass of UserList.

    Attributes:
        caches      --- List of found caches.
        count       --- Number of found caches.

    Methods:
        get_caches  --- Parse and return list of found caches.
        get_count   --- Parse and return number of found caches.

    """

    def __init__(self, datasource=None):
        """
        Keyworded arguments:
            datasource  --- Datasource instance, or None.

        """
        self._log = getLogger("gcparser.parser.myfinds")
        BaseParser.__init__(self, datasource=datasource)
        self._caches = None
        self._count = None

    def _load(self):
        """ Loads data from webpage. """
        BaseParser._load(self, "http://www.geocaching.com/my/logs.aspx?s=1", auth=True)

    @property
    def data(self):
        return self.caches

    @property
    def caches(self):
        """ List of found caches. """
        if self._caches is None:
            self._caches = self.get_caches()
        return self._caches

    def get_caches(self):
        """
        Parse and return list of found caches.

        """
        self._load()
        caches = []
        if self.count > 0:
            cache = None
            for line in self._data.splitlines():
                match = _pcre("logs_found").match(line)
                if match is not None:
                    cache = {"sequence":self.count-len(caches)}
                    self._log.debug("NEW cache record.")
                    self._log.log_parser("sequence = {0}".format(cache["sequence"]))

                if cache is not None:
                    if "f_date" not in cache:
                        match = _pcre("logs_date").match(line)
                        if match is not None:
                            cache["f_date"] = "{0:04d}-{1:02d}-{2:02d}".format(int(match.group(3)), int(match.group(1)), int(match.group(2)))
                            self._log.log_parser("f_date = {0}".format(cache["f_date"]))

                    if "guid" not in cache:
                        match = _pcre("logs_name").match(line)
                        if match is not None:
                            cache["guid"] = match.group(1)
                            cache["name"] = _unescape(match.group(4)).strip()
                            cache["disabled"] = 0
                            cache["archived"] = 0
                            if match.group(2):
                                cache["disabled"] = 1
                                if match.group(3):
                                    cache["archived"] = 1
                            self._log.log_parser("guid = {0}".format(cache["guid"]))
                            self._log.log_parser("name = {0}".format(cache["name"]))
                            self._log.log_parser("disabled = {0}".format(cache["disabled"]))
                            self._log.log_parser("archived = {0}".format(cache["archived"]))

                    match = _pcre("logs_log").match(line)
                    if match is not None:
                        cache["f_luid"] = match.group(1)
                        self._log.log_parser("f_luid = {0}".format(cache["f_luid"]))
                        self._log.debug("END of cache record '{0}'.".format(cache["name"]))
                        caches.append(cache)
                        cache = None
        return caches

    def __len__(self):
        return self.count

    @property
    def count(self):
        """ Number of found caches. """
        if self._count is None:
            self._count = self.get_count()
        return self._count

    def get_count(self):
        """
        Parse and return number of found caches.

        """
        self._load()
        return len(_pcre("logs_found").findall(self._data))

    # Override unsupported UserList methods
    def __add__(self, other):
        raise NotImplemented
    def __radd__(self, other):
        raise NotImplemented
    def __mul__(self, n):
        raise NotImplemented



########################################
# SeekParser                           #
########################################
# <td class="PageBuilderWidget"><span>Total Records: <b>5371</b> - Page: <b>1</b> of <b>269</b>
_pcre_masks["search_totals"] = ("<td class=\"PageBuilderWidget\"><span>Total Records: <b>([0-9]+)</b> - Page: <b>[0-9]+</b> of <b>([0-9]+)</b>", re.I)
# <img src="/images/icons/compass/N.gif" alt="Direction and Distance" />
_pcre_masks["list_start"] = ("\s*<img src=\"/images/icons/compass/N\.gif\" alt=\"Direction and Distance\" />", re.I)
_pcre_masks["list_end"] = ("\s*</table>", re.I)
_pcre_masks["list_user_start"] = ("\s+<br\s*/>\s*", re.I)
# <img src="/images/icons/compass/NW.gif" alt="NW" />NW<br />0.19mi
_pcre_masks["list_compass"] = ("\s*<br />(Here)|\s*<img src=['\"]/images/icons/compass/[EWNS]+.gif['\"][^>]*>[EWNS]+<br />([0-9.]+)(ft|mi)", re.I)
# <img src="/images/small_profile.gif" alt="Premium Member Only Cache" with="15" height="13" />
_pcre_masks["list_PMonly"] = ("<img src=['\"]/images/small_profile.gif['\"] alt=['\"]Premium Member Only Cache['\"][^>]*>", re.I)
# <img src="http://www.geocaching.com/images/wpttypes/794.gif" alt="Police Geocaching Squad 2007 Geocoin (1 item(s))" />
_pcre_masks["list_item"] = ("<img src=\"[^\"]+wpttypes/[^\"]+\"[^>]*>", re.I)
# (3.5/1.5)<br />
_pcre_masks["list_DT"] = ("^\s+\(([12345.]+)/([12345.]+)\)<br />", re.I)
# <img src="/images/icons/container/small.gif" alt="Size: Small" />
_pcre_masks["list_size"] = ("^\s+<img[^>]*src=['\"][^'\"]*/icons/container/[^'\"]*['\"][^>]*alt=['\"]Size: ([^'\"]+)['\"][^>]*>", re.I)
# 25 Jun 10 <img src="/images/new3.gif" alt="New!" />
_pcre_masks["list_hidden"] = ("([0-9]+) ([A-Za-z]+) ([0-9]+)( <img[^>]*alt=['\"]New!['\"][^>]*>)?", re.I)
# <a href="/seek/cache_details.aspx?guid=673d255f-45e8-4b91-8c61-a47878ec65de"><span class="Strike">Pribehy Franty Omacky 3.: Dochazi benzin</span></a>
_pcre_masks["list_name"] = ("<a href=['\"][^'\"]*/seek/cache_details.aspx\?guid=([a-z0-9-]+)['\"]>(<span class=\"(OldWarning )?Strike\">)?([^<]+)(</span>)?</a>", re.I)
# by Franta Omacka
_pcre_masks["list_owner"] = ("^\s*by (.*)\s*$", re.I)
# (GC1NF8Y)<br />
_pcre_masks["list_waypoint"] = ("^\s*\((GC[0-9A-Z]+)\)<br />\s*$", re.I)
# Hlavni mesto Praha
_pcre_masks["list_location"] = ("^\s*(([^,.]+), )?([^.]+)\s*$", re.I)
# 30 Oct 09<br />
_pcre_masks["list_foundDate"] = ("^\s*([0-9]+) ([A-Za-z]+) ([0-9]+)<br />\s*$", re.I)
# 2 days ago*<br />
_pcre_masks["list_foundDays"] = ("^\s*([0-9]+) days ago((<strong>)?\*(</strong>)?)?<br />\s*$", re.I)
# Yesterday<strong>*</strong><br />
# Today<strong>*</strong><br />
_pcre_masks["list_foundWords"] = ("^\s*((Yester|To)day)((<strong>)?\*(</strong>)?)?<br />\s*$", re.I)
# End
_pcre_masks["list_cacheEnd"] = ("</tr>", re.I)


class SeekParser(BaseParser, UserList):
    """
    Parse seek query.

    Subclass of UserList.

    Attributes:
        caches      --- List of found caches.
        count       --- Number of found caches.
        pages       --- Number of pages in result.

    Methods:
        get_page    --- Parse and return list of found caches from page.
        get_caches  --- Parse and return list of all found caches.
        get_count   --- Parse and return number of found caches.
        get_pages   --- Parse and return number of pages in result.

    """

    def __init__(self, type_="coord", data={}, datasource=None):
        """
        Keyworded arguments:
            type_       --- Type of seek query ('coord', 'user', 'owner').
            data        --- Additional data for query.
            datasource  --- Datasource instance, or None.

        """
        self._log = getLogger("gcparser.parser.seek")
        BaseParser.__init__(self, datasource=datasource)
        self._url = "http://www.geocaching.com/seek/nearest.aspx?"
        self._type = type_
        if type_ == "coord":
            if "lat" not in data or "lon" not in data:
                self._log.critical("'coord' type seek needs 'lat' and 'lon' parameters.")
            if not isinstance(data["lat"], float) or not isinstance(data["lon"], float):
                self._log.critical("LatLon needs to be float.")
            if not "dist" in data or not isinstance(data["dist"], int):
                data["dist"] = ""
            self._url += "origin_lat={lat:.5f}&origin_long={lon:.5f}&dist={dist}&submit3=Search".format(**data)
        elif type_ == "user":
            if "user" not in data:
                self._log.critical("'user' type seek needs 'user' parameter.")
            self._url += urlencode({"ul":data["user"], "submit4":"Go"})
        elif type_ == "owner":
            if "user" not in data:
                self._log.critical("'owner' type seek needs 'user' parameter.")
            self._url += urlencode({"u":data["user"], "submit4":"Go"})
        else:
            self._log.critical("Uknown seek type.")
        self._caches = None
        self._count = None
        self._pages = None
        self._data = []
        self._post_data = {}

    def _load_next_page(self):
        """ Loads data from webpage. """
        if len(self._data) == 0:
            self._data.append(self.datasource.request(self._url))
        else:
            if len(self._data) >= self.pages:
                return
            self._data.append(self.datasource.request(self._url, data=self._post_data))
        # POST data for next page
        self._post_data = {}
        for hidden_input in _pcre("hidden_input").findall(self._data[-1]):
            self._post_data[hidden_input[0]] = hidden_input[1]
        self._post_data["__EVENTTARGET"] = "ctl00$ContentBody$pgrTop$ctl08"

    @property
    def data(self):
        return self.caches

    @property
    def caches(self):
        """ List of all found caches. """
        if self._caches is None:
            self._caches = self.get_caches()
        return self._caches

    def get_caches(self):
        """
        Parse and return list of all found caches.

        """
        caches = []
        for page in range(1, self.pages+1):
            caches.extend(self.get_page(page))
        return caches

    def get_page(self, page):
        """
        Parse and return list of found caches from page.

        Arguments:
            page        --- Page number.

        """
        if page > self.pages:
            return []
        while page > len(self._data):
            self._load_next_page()
        caches = []
        cache = None
        started = False
        for line in self._data[page-1].splitlines():
            if started:
                match = _pcre("list_end").match(line)
                if match is not None:
                    self._log.debug("Cache table ended.")
                    started = False
                    cache = None
                elif self._type == "coord":
                    match = _pcre("list_compass").match(line)
                    if match is not None:
                        self._log.debug("NEW cache record.")
                        cache = {"PMonly":False, "items":False, "found":False}
                        if match.group(1) == "Here":
                            cache["distance"] = 0.0
                        else:
                            if match.group(3) == "ft":
                                cache["distance"] = float(match.group(2)) * 0.0003048
                            else:
                                cache["distance"] = float(match.group(2)) * 1.609344
                        self._log.log_parser("distance = {0:.3f}".format(cache["distance"]))
                else:
                    match = _pcre("list_user_start").match(line)
                    if match is not None:
                        self._log.debug("NEW cache record.")
                        cache = {"PMonly":False, "items":False, "found":False}
            else:
                match = _pcre("list_start").match(line)
                if match is not None:
                    self._log.debug("Cache table started.")
                    started = True

            if cache is not None:
                if "type" not in cache:
                    match = _pcre("cache_type").search(line)
                    if match is not None:
                        cache["type"] = _unescape(match.group(1)).strip()
                        # GS weird changes bug
                        if cache["type"] == "Unknown Cache":
                            cache["type"] = "Mystery/Puzzle Cache"
                        self._log.log_parser("type = {0}".format(cache["type"]))
                elif "difficulty" not in cache:
                    match = _pcre("list_PMonly").search(line)
                    if match is not None:
                        cache["PMonly"] = True
                        self._log.log_parser("PM only cache.")

                    match = _pcre("list_item").search(line)
                    if match is not None:
                        cache["items"] = True
                        self._log.log_parser("Has items inside.")
                    match = _pcre("list_DT").search(line)
                    if match is not None:
                        cache["difficulty"] = float(match.group(1))
                        cache["terrain"] = float(match.group(2))
                        self._log.log_parser("difficulty = {0:.1f}".format(cache["difficulty"]))
                        self._log.log_parser("terrain = {0:.1f}".format(cache["terrain"]))
                elif "size" not in cache:
                    match = _pcre("list_size").search(line)
                    if match is not None:
                        cache["size"] = match.group(1).strip()
                        self._log.log_parser("size = {0}".format(cache["size"]))
                elif "hidden" not in cache:
                    match = _pcre("list_hidden").search(line)
                    if match is not None:
                        cache["hidden"] = "{0:04d}-{1:02d}-{2:02d}".format(int(match.group(3))+2000, _months_abbr[match.group(2)], int(match.group(1)))
                        self._log.log_parser("hidden = {0}".format(cache["hidden"]))
                elif "name" not in cache:
                    match = _pcre("list_name").search(line)
                    if match is not None:
                        cache["guid"] = match.group(1)
                        cache["name"] = _unescape(match.group(4)).strip()
                        if match.group(2):
                            cache["disabled"] = 1
                        else:
                            cache["disabled"] = 0
                        if match.group(3):
                            cache["archived"] = 1
                        else:
                            cache["archived"] = 0
                        self._log.log_parser("guid = {0}".format(cache["guid"]))
                        self._log.log_parser("name = {0}".format(cache["name"]))
                        self._log.log_parser("disabled = {0}".format(cache["disabled"]))
                        self._log.log_parser("archived = {0}".format(cache["archived"]))
                elif "owner" not in cache:
                    match = _pcre("list_owner").search(line)
                    if match is not None:
                        cache["owner"] = _unescape(match.group(1)).strip()
                        self._log.log_parser("owner = {0}".format(cache["owner"]))
                elif "waypoint" not in cache:
                    match = _pcre("list_waypoint").search(line)
                    if match is not None:
                        cache["waypoint"] = match.group(1).strip()
                        self._log.log_parser("waypoint = {0}".format(cache["waypoint"]))
                elif "country" not in cache:
                    match = _pcre("list_location").search(line)
                    if match is not None:
                        if match.group(2) is not None:
                            cache["province"] = _unescape(match.group(2)).strip()
                        else:
                            cache["province"] = ""
                        cache["country"] = _unescape(match.group(3)).strip()
                        self._log.log_parser("country = {0}".format(cache["country"]))
                        self._log.log_parser("province = {0}".format(cache["province"]))
                elif not cache["found"]:
                    match = _pcre("list_foundDate").search(line)
                    if match is not None:
                        cache["found"] = "{0:04d}-{1:02d}-{2:02d}".format(int(match.group(3))+2000, _months_abbr[match.group(2)], int(match.group(1)))
                    else:
                        match = _pcre("list_foundDays").search(line)
                        if match is not None:
                            found_date = date.today() - timedelta(days=int(match.group(1)))
                            cache["found"] = found_date.isoformat()
                        else:
                            match = _pcre("list_foundWords").search(line)
                            if match is not None:
                                found_date = date.today()
                                if match.group(1) == "Yesterday":
                                    found_date = found_date - timedelta(days=1)
                                cache["found"] = found_date.isoformat()
                    if cache["found"]:
                        self._log.log_parser("found = {0}".format(cache["found"]))

                match = _pcre("list_cacheEnd").search(line)
                if match is not None:
                    if (self._type != "coord" or "distance" in cache) and "type" in cache and "difficulty" in cache and "size" in cache and "hidden" in cache and "name" in cache and "owner" in cache and "waypoint" in cache and "country" in cache and "province" in cache:
                        self._log.debug("END of cache record {0}.".format(cache["name"]))
                        caches.append(cache)
                        cache = None
                    else:
                        self._log.warn("Seems like end of cache record, but some keys were not found.")

        if not (len(caches) == 20 or (len(caches) == self.count % 20 and page == self.pages)):
            self._log.error("Seems like I missed some caches in the list, got only {0} caches on page {1}/{2}.".format(len(caches), page, self.pages))
        return caches

    def __len__(self):
        return self.count

    @property
    def count(self):
        """ Number of found caches. """
        if self._count is None:
            self._count = self.get_count()
        return self._count

    def get_count(self):
        """
        Parse and return number of found caches.

        """
        return self._parse_totals()[0]

    @property
    def pages(self):
        """ Number of pages in result. """
        if self._pages is None:
            self._pages = self.get_pages()
        return self._pages

    def get_pages(self):
        """
        Parse and return number of pages in result.

        """
        return self._parse_totals()[1]

    def _parse_totals(self):
        """ Parse count and pages. """
        if len(self._data) == 0:
            self._load_next_page()
        match = _pcre("search_totals").search(self._data[0])
        if match is not None:
            return (int(match.group(1)), int(match.group(2)))
        else:
            self._log.warn("Could not find count and page_count... assuming empty result.")
            self._caches = []
            return (0, 0)

    # Override unsupported UserList methods
    def __add__(self, other):
        raise NotImplemented
    def __radd__(self, other):
        raise NotImplemented
    def __mul__(self, n):
        raise NotImplemented



########################################
# ProfileEdit                          #
########################################
class ProfileEdit(BaseParser):
    """
    Profile edit.

    Attributes:
        data        --- Data to save in user's geocaching.com profile.

    Methods:
        save        --- Save data in user's geocaching.com profile.

    """

    def __init__(self, data, datasource=None):
        """
        Arguments:
            data        --- Data to save in user's geocaching.com profile.

        Keyworded arguments:
            datasource  --- Datasource instance, or None.

        """
        self._log = getLogger("gcparser.parser.profileedit")
        BaseParser.__init__(self, datasource=datasource)
        self.data = data

    def save(self):
        """
        Saves data in user's geocaching.com profile.

        """
        self._load("http://www.geocaching.com/account/editprofiledetails.aspx", auth=True)
        data = {}
        for hidden_input in _pcre("hidden_input").findall(self._data):
            data[hidden_input[0]] = hidden_input[1]
        data["ctl00$ContentBody$uxProfileDetails"] = str(self.data)
        data["ctl00$ContentBody$uxSave"] = "Save Changes"
        self._data = None
        self._load("http://www.geocaching.com/account/editprofiledetails.aspx", auth=True, data=data)



############################################################
### Variables.                                           ###
############################################################

parsers = {}
parsers["myfinds"] = MyFindsParser
parsers["seek"] = SeekParser
parsers["cache"] = CacheParser
parsers["profileedit"] = ProfileEdit
""" Dictionary containing parser classes. """



############################################################
### Exceptions.                                          ###
############################################################

class CredentialsError(ValueError):
    """
    Raised on invalid credentials.

    """
    pass


class LoginError(AssertionError):
    """
    Raised when geocaching.com login fails.

    """
    pass


class DatasourceError(ValueError):
    """
    Raised on invalid datasource.

    """
    pass