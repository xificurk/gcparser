#!/usr/bin/env python3
# -*- coding: utf-8 -*-

""" Import GCparser
"""
from gcparser import GCparser

""" Create GCparser class, you can also pass the third dataDir argument, then
    GCparser will use that directory to store login cookies, and reuse them,
    if possible.
"""
gcp = GCparser("username", "secret")

""" Let's take a look at your finds
"""
myfinds = gcp.parse("myFinds").getList()
print("MyFinds:")
print(myfinds)

print()

""" And now, parse details about some cache, you can pass guid or waypoint.
"""
details = gcp.parse("cache", "ed5b20b7-fdca-4e59-b518-3412154d49d0").getDetails()
print("Cache:")
print(details)

""" Let's update our profile.
"""
gcp.parse("editProfile", "Pyggs profile update test.").save()

""" Let's find some caches by coordinates.
"""
search = gcp.parse("seek", type="coord", data={"lat":50.084, "lon":14.434, "dist":3})
print("Seek by coord:")
print(search.getPageCount())
print(search.getCacheCount())
print(search.getList())