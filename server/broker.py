"""Root-only Docker broker. Web requests cannot choose mounts or Docker arguments."""
import grp
import json
import os
import re
import socketserver
import subprocess
import threading
import time
import uuid
from pathlib import Path

SOCKET = os.environ.get('CN_SOCKET', '/run/codynick-server/runner.sock')
IMAGE = os.environ.get('CN_IMAGE', 'codynick-classroom:0.1.0')
MAX_JOBS = int(os.environ.get('CN_MAX_JOBS', '2'))
GRACE = 120
JOBS = {}
LOCK = threading.RLock()


def docker(*args, timeout=20, input=None):
    result = subprocess.run(['docker', *args], input=input, capture_output=True,
                            text=True, timeout=timeout, check=True)
    return result.stdout


def cleanup(job):
    try:
        docker('rm', '-f', job['name'])
    except (subprocess.SubprocessError, OSError):
        pass
    job['running'] = False


def collect(job):
    try:
        process = subprocess.Popen(['docker', 'start', '-a', job['name']],
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        while True:
            chunk = process.stdout.read1(4096)
            if not chunk:
                break
            with LOCK:
                job['output'] = (job['output'] + chunk.decode('utf-8', 'replace'))[-131072:]
        process.wait()
        with LOCK:
            job['output'] += '\n[Program finished]\n'
    except Exception as exc:
        with LOCK:
            job['output'] += '\nRunner error: ' + str(exc)
    finally:
        with LOCK:
            cleanup(job)


def request(data):
    uid = str(data.get('uid', ''))
    if not re.fullmatch(r'[1-9][0-9]{0,8}', uid):
        raise ValueError('Invalid user')
    action = data.get('action')
    with LOCK:
        job = JOBS.get(uid)
        if action == 'stop':
            if job:
                cleanup(job)
            return {'ok': True}
        if action == 'status':
            if job:
                job['seen'] = time.monotonic()
            return dict(ok=True, running=bool(job and job['running']),
                        output=job['output'] if job else '')
        if action == 'input':
            values = data.get('values', {})
            temperature = float(values.get('temperature', 21.5))
            direction = values.get('joystick', 'neutral')
            if not -55 <= temperature <= 125 or direction not in ('neutral', 'up', 'down', 'left', 'right', 'click'):
                raise ValueError('Invalid input')
            if job and job['running']:
                docker('exec', '-i', job['name'], 'python', '-c',
                       "import sys,os;open('/workspace/input.new','w').write(sys.stdin.read());os.replace('/workspace/input.new','/workspace/input.json')",
                       input=json.dumps(dict(temperature=temperature, joystick=direction)))
            return {'ok': True}
        if action != 'run':
            raise ValueError('Unknown action')
        code = data.get('code')
        if not isinstance(code, str) or len(code.encode()) > 65536:
            raise ValueError('Program too large')
        if job and job['running']:
            cleanup(job)
        if sum(j['running'] for j in JOBS.values()) >= MAX_JOBS:
            raise ValueError('All execution slots are busy. Please try again shortly.')
        name = 'cn-' + uid + '-' + uuid.uuid4().hex[:12]
        job = dict(name=name, running=True, output='', seen=time.monotonic(), started=time.monotonic())
        try:
            docker('create', '--name', name, '--label', 'codynick.classroom=1',
                   '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', '--pids-limit', '32',
                   '--memory', '128m', '--memory-swap', '128m', '--cpus', '0.5',
                   '--ulimit', 'nofile=64:64', '--log-driver', 'none',
                   '--tmpfs', '/workspace:rw,nosuid,nodev,noexec,size=32m,mode=1777',
                   '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=8m', IMAGE,
                   'python', '-u', '-c', 'import os,time;\nwhile not os.path.exists("/workspace/main.py"): time.sleep(0.05)\nexec(compile(open("/workspace/main.py").read(),"main.py","exec"))')
            JOBS[uid] = job
            threading.Thread(target=collect, args=(job,), daemon=True).start()
            # The container waits for this file before executing the supplied program.
            for _ in range(40):
                try:
                    docker('exec', '-i', name, 'python', '-c',
                           "import sys,os;open('/workspace/main.new','w').write(sys.stdin.read());os.replace('/workspace/main.new','/workspace/main.py')", input=code)
                    break
                except subprocess.CalledProcessError:
                    time.sleep(0.1)
            else:
                raise RuntimeError('Execution container did not start')
        except Exception:
            cleanup(job)
            raise
        return {'ok': True}


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(30)
        try:
            raw = self.rfile.readline(80000)
            if len(raw) >= 80000:
                raise ValueError('Request too large')
            response = request(json.loads(raw))
        except Exception as exc:
            response = dict(ok=False, error=str(exc))
        self.wfile.write((json.dumps(response) + '\n').encode())


def reap():
    while True:
        time.sleep(5)
        with LOCK:
            for uid, job in list(JOBS.items()):
                now = time.monotonic()
                if job['running'] and (now - job['seen'] > GRACE or now - job['started'] > 1800):
                    job['output'] += '\n[Stopped: disconnected or 30-minute runtime limit]\n'
                    cleanup(job)
                if not job['running'] and now - job['seen'] > 3600:
                    del JOBS[uid]


if __name__ == '__main__':
    for name in docker('ps', '-aq', '--filter', 'label=codynick.classroom=1').split():
        docker('rm', '-f', name)
    Path(SOCKET).unlink(missing_ok=True)
    with socketserver.ThreadingUnixStreamServer(SOCKET, Handler) as server:
        os.chown(SOCKET, 0, grp.getgrnam('codynick-web').gr_gid)
        os.chmod(SOCKET, 0o660)
        threading.Thread(target=reap, daemon=True).start()
        server.serve_forever()
