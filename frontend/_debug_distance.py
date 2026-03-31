import requests, json, math

base = 'https://www.onemap.gov.sg'
email = 'e1122477@u.nus.edu'
pw = 'Lol232566!abcde'

resp = requests.post(f'{base}/api/auth/post/getToken', json={'email': email, 'password': pw}, timeout=10)
token = resp.json().get('access_token')

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

# Test with a common HDB location (e.g., Toa Payoh)
test_lat, test_lon = 1.3343, 103.8563
radius_km = 2.0

themes = ['moh_hospitals', 'vaccination_polyclinics']
results = []

for theme in themes:
    url = f'{base}/api/public/themesvc/retrieveTheme?queryName={theme}'
    headers = {'Authorization': f'Bearer {token}'}
    resp = requests.get(url, headers=headers, timeout=10)
    data = resp.json()
    items = data.get('SrchResults', [])
    print(f'\n=== {theme}: {len(items)} items ===')

    for idx, item in enumerate(items):
        coords = item.get('LatLng')
        if not coords:
            continue
        parts = str(coords).split(',')
        if len(parts) != 2:
            continue
        try:
            lat_ = float(parts[0].strip())
            lon_ = float(parts[1].strip())
        except ValueError:
            continue
        dist = haversine_km(test_lat, test_lon, lat_, lon_)
        name = item.get('NAME', '?')
        if dist <= radius_km:
            print(f'  WITHIN {radius_km}km: {name} ({dist:.2f}km)')
            results.append(name)
        elif dist <= 5.0:
            print(f'  Near ({dist:.2f}km): {name}')

print(f'\nTotal within {radius_km}km of ({test_lat},{test_lon}): {len(results)}')
if not results:
    print('NO RESULTS - the 2km radius may be too small for this location!')
