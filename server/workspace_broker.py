"""Fixed Docker operations for private copies of the original RPi tools."""
import base64
import grp
import io
import json
import os
import re
import secrets
import signal
import socketserver
import sqlite3
import subprocess
import tarfile
import threading
import time
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs

SOCKET = os.environ.get('CN_SOCKET', '/run/codynick-server/runner.sock')
IMAGE = os.environ.get('CN_IMAGE', 'codynick-classroom:0.2.0')
STORE = Path(os.environ.get('CN_WORKSPACES', '/var/lib/codynick-workspaces'))
JOBS = {}
LOCK = threading.RLock()
MAX_ARCHIVE = 70 * 1024 * 1024


def docker(*args, timeout=50, input=None):
    return subprocess.run(['docker', *args], input=input, capture_output=True,
                          timeout=timeout, check=True).stdout


def validate_archive(raw):
    if len(raw) > MAX_ARCHIVE:
        raise ValueError('Workspace snapshot exceeds quota')
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        total = 0
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or '..' in path.parts or not (member.isfile() or member.isdir()):
                raise ValueError('Unsafe workspace archive entry')
            total += member.size
            if total > 64 * 1024 * 1024:
                raise ValueError('Workspace data exceeds quota')


def credentials(uid):
    STORE.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = STORE / (uid + '.json')
    if path.exists():
        return json.loads(path.read_text())
    name, password = 'cn_' + uid, secrets.token_hex(24)
    sql = (f"CREATE DATABASE IF NOT EXISTS `{name}`; CREATE USER IF NOT EXISTS '{name}'@'localhost' IDENTIFIED BY '{password}'; "
           f"ALTER USER '{name}'@'localhost' IDENTIFIED BY '{password}'; GRANT ALL ON `{name}`.* TO '{name}'@'localhost';")
    subprocess.run(['mariadb', '--protocol=socket', '-uroot'], input=sql.encode(), check=True, capture_output=True)
    data = dict(name=name, password=password)
    path.write_text(json.dumps(data))
    path.chmod(0o600)
    return data


def call(job, payload):
    raw = docker('exec', '-i', job['name'], 'python', '/opt/agent/call.py', input=json.dumps(payload).encode())
    result = json.loads(raw)
    if not result.get('ok'):
        raise ValueError(result.get('error', 'Workspace operation failed'))
    return result


def snapshot(uid, job):
    raw = docker('exec', job['name'], 'tar', '-cf', '-', '-C', '/home/client', '.')
    validate_archive(raw)
    temporary = STORE / (uid + '.tar.new')
    temporary.write_bytes(raw)
    temporary.replace(STORE / (uid + '.tar'))


def migrate(uid, job):
    database = Path('/var/lib/codynick-server/classroom.sqlite')
    if not database.exists():
        return
    with sqlite3.connect(database) as conn:
        rows = conn.execute('SELECT name,content,kind FROM projects WHERE user_id=?', (uid,)).fetchall()
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as archive:
        for name, content, kind in rows:
            safe = re.sub(r'[^\w .-]', '_', name).strip('. ') or 'Untitled'
            suffix = '.py' if kind == 'python' else '.codynick'
            filename = safe if safe.endswith(suffix) else safe + suffix
            raw = content.encode()
            info = tarfile.TarInfo('userfiles/Migrated projects/' + filename)
            info.size, info.mode = len(raw), 0o600
            archive.addfile(info, io.BytesIO(raw))
    if rows:
        docker('exec', '-i', job['name'], 'tar', '-xf', '-', '--no-same-owner', '-C', '/home/client', input=stream.getvalue())


def provision(uid, role='student'):
    config = credentials(uid)
    name = 'cn-workspace-' + uid
    job = dict(name=name, seen=time.monotonic(), started=time.monotonic(), lock=threading.RLock())
    try:
        docker('rm', '-f', name)
    except subprocess.CalledProcessError:
        pass
    privacy = [] if role == 'teacher' else ['--tmpfs', '/opt/rpi/ide/teachers:ro,nosuid,nodev,size=1m']
    docker('create', '--name', name, '--label', 'codynick.classroom=1',
           '--network', 'none', '--read-only', '--cap-drop', 'ALL',
           '--security-opt', 'no-new-privileges', '--pids-limit', '64',
           '--memory', '256m', '--memory-swap', '256m', '--cpus', '0.5',
           '--ulimit', 'nofile=128:128', '--log-driver', 'none',
           '--tmpfs', '/home/client:rw,nosuid,nodev,noexec,size=64m,mode=1777',
           '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=16m,mode=1777',
           '--mount', 'type=bind,source=/run/mysqld,target=/run/mysqld,readonly',
           '--env', 'CN_DB_NAME=' + config['name'], '--env', 'CN_DB_USER=' + config['name'],
           '--env', 'CN_DB_PASSWORD=' + config['password'], *privacy, IMAGE)
    docker('start', name)
    for _ in range(50):
        try:
            call(job, dict(action='status'))
            break
        except (ValueError, subprocess.CalledProcessError):
            time.sleep(.1)
    else:
        docker('rm', '-f', name)
        raise RuntimeError('Workspace did not start')
    saved = STORE / (uid + '.tar')
    if saved.exists():
        raw = saved.read_bytes()
        validate_archive(raw)
        docker('exec', '-i', name, 'tar', '-xf', '-', '--no-same-owner', '-C', '/home/client', input=raw)
        call(job, dict(action='restore'))
    else:
        migrate(uid, job)
    JOBS[uid] = job
    return job


def request(data):
    uid = str(data.get('uid', ''))
    if not re.fullmatch(r'[1-9][0-9]{0,8}', uid):
        raise ValueError('Invalid user')
    action = data.get('action')
    if action not in ('run', 'stop', 'status', 'php', 'sim', 'heartbeat'):
        raise ValueError('Unsupported operation')
    with LOCK:
        job = JOBS.get(uid)
        if not job and action in ('stop', 'status', 'heartbeat'):
            return dict(ok=True, running=False, output='')
        if not job:
            job = provision(uid, data.get('role', 'student'))
        job['seen'] = time.monotonic()
    with job['lock']:
        payload = {k: v for k, v in data.items() if k != 'uid'}
        if action == 'heartbeat':
            return dict(ok=True)
        if action == 'run':
            code = data.get('code')
            if not isinstance(code, str) or len(code.encode()) > 1048576:
                raise ValueError('Program exceeds quota')
        if action == 'php':
            path = PurePosixPath(data.get('path', ''))
            allowed = {'index.php', 'code/index.php', 'code/media.php', 'blocks/index.php',
                       'blocks/designs.php', 'blocks/stage.php', 'dashboard/index.php',
                       'dashboard/cards.php', 'docs/index.php', 'teachers/index.php', 'gadget-tests/index.php'}
            if str(path) not in allowed:
                raise ValueError('Page not allowed')
            if data.get('method') not in ('GET', 'POST'):
                raise ValueError('Method not allowed')
        try:
            result = call(job, payload)
        except (ValueError, subprocess.SubprocessError):
            if action != 'stop':
                raise
            # Stop must still work after an exhausted process limit or dead agent.
            docker('rm', '-f', job['name'])
            with LOCK:
                JOBS.pop(uid, None)
            return dict(ok=True)
        query = parse_qs(data.get('query', ''))
        changes_files = (action == 'php' and data.get('method') == 'POST' and
            ((data['path'] in ('code/index.php', 'code/media.php') and query.get('action', [''])[0] in
              ('run', 'save', 'create', 'rename', 'move', 'delete', 'upload')) or
             (data['path'] == 'blocks/index.php' and query.get('api', [''])[0] in ('run', 'save')) or
             (data['path'] == 'blocks/designs.php' and query.get('action', [''])[0] in ('save', 'delete'))))
        if action == 'run' or changes_files:
            snapshot(uid, job)
        if action == 'sim' and data.get('method') == 'POST':
            body = json.loads(base64.b64decode(data.get('body', '')))
            if body.get('action') == 'scene':
                snapshot(uid, job)
        return result


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(90)
        try:
            raw = self.rfile.readline(75 * 1024 * 1024)
            if len(raw) >= 75 * 1024 * 1024:
                raise ValueError('Request too large')
            response = request(json.loads(raw))
        except Exception as exc:
            response = dict(ok=False, error=str(exc))
        self.wfile.write((json.dumps(response) + '\n').encode())


def reap():
    while True:
        time.sleep(5)
        with LOCK:
            jobs = list(JOBS.items())
        for uid, job in jobs:
            if time.monotonic() - job['seen'] > 120:
                with job['lock']:
                    try:
                        call(job, dict(action='stop'))
                    except Exception:
                        pass
            if time.monotonic() - job['seen'] > 600:
                with job['lock']:
                    with LOCK:
                        if JOBS.get(uid) is not job or time.monotonic() - job['seen'] <= 600:
                            continue
                    try:
                        snapshot(uid, job)
                        docker('rm', '-f', job['name'])
                        with LOCK:
                            JOBS.pop(uid, None)
                    except Exception:
                        pass


if __name__ == '__main__':
    STORE.mkdir(mode=0o700, parents=True, exist_ok=True)
    for name in docker('ps', '-aq', '--filter', 'label=codynick.classroom=1').decode().split():
        docker('rm', '-f', name)
    Path(SOCKET).unlink(missing_ok=True)
    with socketserver.ThreadingUnixStreamServer(SOCKET, Handler) as server:
        os.chown(SOCKET, 0, grp.getgrnam('codynick-web').gr_gid)
        os.chmod(SOCKET, 0o660)
        threading.Thread(target=reap, daemon=True).start()
        signal.signal(signal.SIGTERM, lambda *args: threading.Thread(target=server.shutdown, daemon=True).start())
        try:
            server.serve_forever()
        finally:
            for uid, job in list(JOBS.items()):
                with job['lock']:
                    try:
                        call(job, dict(action='stop'))
                        snapshot(uid, job)
                        docker('rm', '-f', job['name'])
                    except Exception:
                        pass
