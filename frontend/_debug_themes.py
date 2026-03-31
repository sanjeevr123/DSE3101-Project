import requests, json

base = 'https://www.onemap.gov.sg'
email = 'e1122477@u.nus.edu'
pw = 'Lol232566!abcde'

resp = requests.post(f'{base}/api/auth/post/getToken', json={'email': email, 'password': pw}, timeout=10)
token = resp.json().get('access_token')

# Check available themes related to health
url = f'{base}/api/public/themesvc/getAllThemesInfo?moreInfo=Y'
headers = {'Authorization': f'Bearer {token}'}
resp = requests.get(url, headers=headers, timeout=15)
data = resp.json()
themes = data.get('Theme_Names', [])
health_themes = [t for t in themes if any(kw in (t.get('THEMENAME','') + t.get('QUERYNAME','')).lower() for kw in ['health', 'hospital', 'clinic', 'poly', 'medical'])]
for t in health_themes:
    print(f"QUERY={t.get('QUERYNAME')}, NAME={t.get('THEMENAME')}")
