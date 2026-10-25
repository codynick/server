import sys
import urllib.request

body = sys.stdin.buffer.read(75 * 1024 * 1024)
request = urllib.request.Request('http://127.0.0.1:8093/', data=body,
                                 headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(request, timeout=45) as response:
    sys.stdout.buffer.write(response.read())
