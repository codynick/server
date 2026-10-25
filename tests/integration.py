"""Linux acceptance against real PHP, simulator, MariaDB and isolated Python."""
import base64
import json
import socket
import time
from urllib.parse import urlencode


def call(uid, action, **data):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(90)
        conn.connect('/run/codynick-server/runner.sock')
        conn.sendall((json.dumps(dict(uid=uid, action=action, **data)) + '\n').encode())
        with conn.makefile() as file:
            result = json.loads(file.readline())
    assert result.get('ok'), result
    return result


def php(uid, path, query='', data=None, role='student', raw=None):
    body = raw if raw is not None else urlencode(data or {}).encode()
    result = call(uid, 'php', path=path, query=query, role=role, uri='/' + path,
                  method='POST' if data is not None or raw is not None else 'GET',
                  content_type='application/json' if raw is not None else 'application/x-www-form-urlencoded',
                  body=base64.b64encode(body).decode())
    result['text'] = base64.b64decode(result['body']).decode()
    assert result.get('status', 200) < 400, result
    return result


uids = (900001, 900002, 900003)
try:
    home = php(uids[0], 'index.php', role='teacher')['text']
    for title in ('On-Device IDE', 'Block Coding', 'On-Device Dashboard', 'Gadget Simulator', 'Student Management'):
        assert title in home, title
    assert 'Student Management</div>' not in php(uids[1], 'index.php')['text']
    for i, uid in enumerate(uids):
        code = f'''import time, CodyNick, Dashboard
cody = CodyNick.Simulator()
CodyNick.RGB_Matrix.set(cody, 0, "{['#FF0000','#00FF00','#0000FF'][i]}")
Dashboard.clear()
card = Dashboard.Card("gauge", "Private temperature", value={20+i})
print("STUDENT_{i}_RUNNING", flush=True)
time.sleep(60)
'''
        php(uid, 'code/index.php', 'action=run', dict(content=code))
    for i, uid in enumerate(uids):
        for attempt in range(30):
            result = call(uid, 'status')
            if f'STUDENT_{i}_RUNNING' in result['output']:
                break
            time.sleep(.5)
        assert result['running'] and f'STUDENT_{i}_RUNNING' in result['output'], result
        state = json.loads(base64.b64decode(call(uid, 'sim', method='GET')['body']))
        assert state['leds'][0] == ['#FF0000','#00FF00','#0000FF'][i], state
        cards = json.loads(php(uid, 'dashboard/cards.php', 'action=state')['text'])
        assert cards['ok'] and len(cards['cards']) == 1, cards
        assert str(20+i) in str(cards['cards'][0]['value']), cards
    php(uids[0], 'code/index.php', 'action=stop', {})
    assert not call(uids[0], 'status')['running']
    assert call(uids[1], 'status')['running']
    assert call(uids[2], 'status')['running']
    php(uids[0], 'code/index.php', 'action=create', dict(path='private.py', type='file'))
    php(uids[0], 'code/index.php', 'action=save', dict(path='private.py', content='print("private")'))
    assert 'private.py' not in php(uids[1], 'code/index.php', 'action=tree')['text']
    saved = dict(name='Private design', workspace={'blocks': {'languageVersion': 0, 'blocks': []}})
    php(uids[0], 'blocks/designs.php', 'action=save', raw=json.dumps(saved).encode())
    assert 'Private design' not in php(uids[1], 'blocks/designs.php', 'action=list')['text']
    for path in ('blocks/index.php', 'docs/index.php', 'teachers/index.php', 'gadget-tests/index.php'):
        text = php(uids[0], path, role='teacher')['text']
        assert '<html' in text.lower(), path
        assert 'Fatal error' not in text, path
    print('Original RPi PHP pages, three simultaneous programs, private files/designs, simulator LEDs, dashboard and Stop: OK')
finally:
    for uid in uids:
        call(uid, 'stop')
