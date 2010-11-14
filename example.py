#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Import parsers, BaseParser and HTTP datasource.
"""
from gcparser import parsers, BaseParser, HTTPDatasource

"""
Create and set default datasource.
"""
BaseParser.datasource = HTTPDatasource(username="petmor", password="petmor")

"""
Create cache parser instance.
"""
cache = parsers["cache"]("ed5b20b7-fdca-4e59-b518-3412154d49d0")
"""
Now download and parse cache details. Since CacheParser is UserDict subclass
you can access the details as dictionary.
"""
print("Cache:")
for name, value in cache.items():
    print("{0}\t{1}".format(name, value))

"""
Create myfinds parser instance.
"""
myfinds = parsers["myfinds"]()
"""
Now download and parse myfinds. Since MyFindsParser is UserList subclass
you can access caches as list.
"""
print("MyFinds ({0} caches):".format(len(myfinds)))
for cache in myfinds:
    print(cache)


"""
Create seek parser instance.
"""
seek = parsers["seek"](type_="coord", data={"lat":50.084, "lon":14.434, "dist":3})
"""
Now download and parse list of caches. Since SeekParser is UserList subclass
you can access caches as list.
"""
print("Seek ({0} in {1} pages):".format(len(seek), seek.pages))
for cache in seek:
    print(cache)

"""
Let's update our profile.
"""
from datetime import datetime
parsers["profileedit"]("Profile edit from {0}.".format(datetime.now().isoformat())).save()