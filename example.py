#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Import GCparser
from GCparser import GCparser

# Create GCparser class, you can also pass the third dataDir argument, then
#   GCparser will use that directory to store login cookies, and reuse them,
#   if possible.
gcp = GCparser("username", "secret")

# Let's take a look at your finds
myfinds = gcp.parse("myFinds").getList()
print("MyFinds:")
print(myfinds)

print()

# And now, parse details about some cache, you can also specify waypoint
#   parameter instead of guid.
details = gcp.parse("cache", guid="ed5b20b7-fdca-4e59-b518-3412154d49d0").getDetails()
print("Cache:")
print(details)