import urllib.request

for path in ['/login', '/register']:
    url = 'http://127.0.0.1:5000' + path
    try:
        with urllib.request.urlopen(url) as resp:
            print(path, resp.status, len(resp.read()))
    except Exception as e:
        print(path, 'ERROR', e)
