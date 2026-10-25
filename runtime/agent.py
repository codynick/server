"""One user's original RPi tools and program runner, entirely inside their container."""
import base64
import importlib.util
import json
import os
import secrets
import shutil
import signal
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HOME = Path('/home/client')
LOCK = threading.RLock()
PROCESS = None
STARTED = 0


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


sys.path.insert(0, '/opt/rpi/simulator')
sim = module('simulator_server', '/opt/rpi/simulator/server.py')
sprite = module('sprite_server', '/opt/rpi/sprite-stage/server.py')
SIM_STATE = None


def stop():
    global PROCESS
    with LOCK:
        if PROCESS and PROCESS.poll() is None:
            try:
                os.killpg(PROCESS.pid, signal.SIGINT)
                PROCESS.wait(timeout=2)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(PROCESS.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        PROCESS = None
        if SIM_STATE:
            with SIM_STATE.lock:
                SIM_STATE.session = None
                SIM_STATE.inputs = []
                SIM_STATE.joystick_inputs = []


def collect(process):
    log = HOME / 'log.log'
    while True:
        chunk = process.stdout.read1(4096)
        if not chunk:
            break
        with LOCK:
            with log.open('ab') as file:
                file.write(chunk)
            if log.stat().st_size > 262144:
                log.write_bytes(log.read_bytes()[-131072:])


def start():
    global PROCESS, STARTED
    stop()
    with LOCK:
        PROCESS = subprocess.Popen([sys.executable, '-u', str(HOME / 'active_script.py')],
                                   cwd=HOME, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        STARTED = time.monotonic()
        threading.Thread(target=collect, args=(PROCESS,), daemon=True).start()


class Control(socketserver.StreamRequestHandler):
    def handle(self):
        action = self.rfile.readline(32).strip()
        if action == b'start':
            start()
        elif action == b'stop':
            stop()
        else:
            self.wfile.write(b'{"ok":false}\n')
            return
        self.wfile.write(b'{"ok":true}\n')


def handle(data):
    action = data.get('action')
    if action == 'restore':
        stop()
        with SIM_STATE.lock:
            SIM_STATE.scene = sim.State(HOME / 'simulator-scene.json').scene
        shutil.copytree('/opt/rpi/examples', HOME / 'userfiles/CodyNick examples', dirs_exist_ok=True)
        return dict(ok=True)
    if action == 'status':
        return dict(ok=True, running=bool(PROCESS and PROCESS.poll() is None),
                    output=(HOME / 'log.log').read_text(errors='replace')[-131072:])
    if action == 'stop':
        stop()
        return dict(ok=True)
    if action == 'run':
        (HOME / 'active_script.py').write_text(data['code'])
        start()
        return dict(ok=True)
    if action == 'sim':
        path = '/state' if data['method'] == 'GET' else '/command'
        body = base64.b64decode(data.get('body', '')) if data['method'] == 'POST' else None
        request = urllib.request.Request('http://127.0.0.1:8091' + path, data=body,
            headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + Path('/tmp/sim-token').read_text()})
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return dict(ok=True, status=response.status, body=base64.b64encode(response.read()).decode(), content_type='application/json')
        except urllib.error.HTTPError as exc:
            return dict(ok=True, status=exc.code, body=base64.b64encode(exc.read()).decode(), content_type='application/json')
    if action != 'php':
        raise ValueError('Unsupported request')
    path = Path('/opt/rpi/ide') / data['path']
    if path.suffix != '.php' or not path.resolve().is_relative_to('/opt/rpi/ide') or not path.is_file():
        raise ValueError('Invalid page')
    env = dict(os.environ)
    body = base64.b64decode(data.get('body', ''))
    env.update(REDIRECT_STATUS='200', SCRIPT_FILENAME=str(path), SCRIPT_NAME='/' + data['path'],
               DOCUMENT_ROOT='/opt/rpi/ide', REQUEST_URI=data.get('uri', '/'),
               REQUEST_METHOD=data['method'], QUERY_STRING=data.get('query', ''),
               CONTENT_TYPE=data.get('content_type', ''), CONTENT_LENGTH=str(len(body)),
               HTTP_HOST='localhost', SERVER_NAME='localhost', SERVER_PORT='80',
               SERVER_PROTOCOL='HTTP/1.1', GATEWAY_INTERFACE='CGI/1.1',
               CN_ROLE=data.get('role', 'student'))
    result = subprocess.run(['php-cgi', '-d', 'cgi.force_redirect=0', '-d', 'display_errors=0',
                              '-d', 'auto_prepend_file=/opt/agent/php-prepend.php',
                              '-d', 'upload_max_filesize=50M', '-d', 'post_max_size=51M'],
                             input=body, capture_output=True, env=env, timeout=35)
    head, separator, output = result.stdout.partition(b'\r\n\r\n')
    if not separator:
        raise RuntimeError('PHP page failed: ' + result.stderr.decode(errors='replace')[:500])
    status, kind, disposition, location = 200, 'text/html; charset=utf-8', '', ''
    for line in head.decode(errors='replace').splitlines():
        key, _, value = line.partition(':')
        if key.lower() == 'status': status = int(value.strip().split()[0])
        if key.lower() == 'content-type': kind = value.strip()
        if key.lower() == 'content-disposition': disposition = value.strip()
        if key.lower() == 'location': location, status = value.strip(), 302
    return dict(ok=True, status=status, content_type=kind, disposition=disposition,
                location=location, body=base64.b64encode(output).decode())


class Agent(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            count = int(self.headers.get('Content-Length', '0'))
            if not 0 < count < 75 * 1024 * 1024:
                raise ValueError('Invalid request size')
            result = handle(json.loads(self.rfile.read(count)))
        except Exception as exc:
            result = dict(ok=False, error=str(exc))
        body = json.dumps(result).encode()
        self.send_response(200)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def initialize():
    global SIM_STATE
    for name in ('userfiles', 'images', 'audio', 'blockdata/designs'):
        (HOME / name).mkdir(parents=True, exist_ok=True)
    for name in ('active_script.py', 'log.log', 'library.log'):
        (HOME / name).touch(exist_ok=True)
    shutil.copytree('/opt/rpi/examples', HOME / 'userfiles/CodyNick examples', dirs_exist_ok=True)
    shutil.copytree('/opt/rpi/gadget-tests', HOME / 'CodyNick Gadget Tests', dirs_exist_ok=True)
    token = secrets.token_hex(32)
    Path('/tmp/sim-token').write_text(token)
    Path('/tmp/device_info.json').write_text(json.dumps(dict(devicename='CodyNick Classroom',
        device_code=os.environ['CN_DB_USER'], hotspot_ssid='Not applicable (server)',
        production_date='2026-10-24', software_version='0.2.0',
        description='Classroom workspace. AI and physical USB are not installed.')))
    SIM_STATE = sim.State(HOME / 'simulator-scene.json')
    for server in (ThreadingHTTPServer(('127.0.0.1', 8091), sim.handler(token, SIM_STATE)),
                   ThreadingHTTPServer(('127.0.0.1', 8092), sprite.handler(sprite.Stage()))):
        threading.Thread(target=server.serve_forever, daemon=True).start()
    Path('/tmp/codynick-script-control.sock').unlink(missing_ok=True)
    control = socketserver.ThreadingUnixStreamServer('/tmp/codynick-script-control.sock', Control)
    threading.Thread(target=control.serve_forever, daemon=True).start()
    def limit_runtime():
        while True:
            time.sleep(5)
            if PROCESS and PROCESS.poll() is None and time.monotonic() - STARTED > 1800:
                stop()
    threading.Thread(target=limit_runtime, daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1', 8093), Agent).serve_forever()


if __name__ == '__main__':
    initialize()
