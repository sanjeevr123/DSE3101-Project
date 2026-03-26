#!/usr/bin/env python3
from app2_updated import _fetch_onemap_healthcare

# Test with Bukit Merah (1.287, 103.833) - central area with hospitals nearby
lat, lon = 1.287, 103.833
results = _fetch_onemap_healthcare(lat, lon, radius_km=3, limit=5)
print(f'Found {len(results)} healthcare amenities within 3km')
for i, r in enumerate(results[:3]):
    print(f'  {i+1}. {r["name"]}')
    print(f'     Address: {r["address"]}')
    print(f'     Coords: ({r["lat"]}, {r["lon"]})')
    print()
