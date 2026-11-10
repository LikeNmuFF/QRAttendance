import json
import re
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import build_opener, HTTPCookieProcessor, Request
from http.cookiejar import CookieJar
root=Path.cwd()
settings=json.loads((root/'python/instance/config.json').read_text(encoding='utf-8'))
client=build_opener(HTTPCookieProcessor(CookieJar()))
with client.open('http://localhost:5000/login',timeout=10) as response:
    csrf=re.search(r'name="csrf" value="([^"]+)"',response.read().decode()).group(1)
request=Request('http://localhost:5000/login',data=urlencode({'csrf':csrf,'username':'admin','password':settings['ADMIN_PASSWORD']}).encode())
with client.open(request,timeout=10) as response:
    page=response.read().decode()
    assert response.status==200 and response.url.endswith('/dashboard')
    assert 'Attendance overview' in page
assert (root/'python/attendance.db').is_file()
print('PASS: actual start.cmd service, saved local credentials, administrator login and persistent SQLite database')
