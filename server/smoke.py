"""Installer acceptance test for the real, restricted execution path."""
import json
import socket
import time


def call(action, **values):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(40)
        conn.connect('/run/codynick-server/runner.sock')
        conn.sendall((json.dumps(dict(uid=99999999, action=action, **values)) + '\n').encode())
        with conn.makefile() as response:
            result = json.loads(response.readline())
        if not result['ok']:
            raise RuntimeError(result.get('error'))
        return result


try:
    call('run', code='import CodyNick, Dashboard, SpriteStage\nprint("CLASSROOM_RUNTIME_OK", flush=True)\n')
    for _ in range(30):
        result = call('status')
        if not result['running']:
            break
        time.sleep(.5)
    if 'CLASSROOM_RUNTIME_OK' not in result['output']:
        raise RuntimeError('Runtime check failed: ' + result['output'])
    print('Restricted classroom runner OK')
finally:
    call('stop')
