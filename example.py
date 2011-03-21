#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Import gcparser.
"""
import gcparser

"""
Set user credentials for HTTP interface.
"""
gcparser.HTTPInterface.set_credentials(gcparser.Credentials("user", "secret"))

"""
Create an instance of CacheDetails
"""
cd = gcparser.CacheDetails()
"""
Now download and parse some listing.
"""
print("Cache:")
for name, value in cd.get("ed5b20b7-fdca-4e59-b518-3412154d49d0").items():
    print("{0}\t{1}".format(name, value))

"""
Create an instance of MyGeocachingLogs.
"""
mgl = gcparser.MyGeocachingLogs()
"""
Now download and parse your finds (logs of type 'Found it', 'Attended', 'Webcam Photo Taken').
"""
finds = mgl.get_finds()
print("Finds ({0} caches):".format(len(finds)))
for log in finds:
    print(log)

"""
Create seek parser instance.
"""
sc = gcparser.SeekCache()
"""
Now download and parse sequence of caches.
"""
seek = sc.coord(50.084, 14.434, 3)
print("Seek ({0} caches):".format(len(seek)))
for cache in seek:
    print(cache)

"""
Create an instance of Profile.
"""
p = gcparser.Profile()
"""
Let's update your profile.
"""
from datetime import datetime
p.update("Profile edit from {0}.".format(datetime.now().isoformat()))