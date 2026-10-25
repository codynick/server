"""Classroom accounts and private projects. Never executes Python on the host."""
import functools
from contextlib import contextmanager
import json
import os
import re
import secrets
import socket
import sqlite3
import time
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

VERSION = '0.1.0'
DATA = Path(os.environ.get('CN_DATA', '/var/lib/codynick-server'))
DATA.mkdir(parents=True, exist_ok=True)
app = Flask(__name__, static_folder='../static', template_folder='../templates')
app.secret_key = os.environ.get('CN_SECRET', '') or secrets.token_hex(32)
app.config.update(MAX_CONTENT_LENGTH=262144, SESSION_COOKIE_HTTPONLY=True,
                  SESSION_COOKIE_SAMESITE='Strict', SESSION_COOKIE_SECURE=os.environ.get('CN_HTTPS') == '1',
                  PERMANENT_SESSION_LIFETIME=28800)
FAILURES = {}


@contextmanager
def db():
    connection = sqlite3.connect(DATA / 'classroom.sqlite', timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize():
    with db() as conn:
        conn.executescript('''
        CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL,
          password TEXT NOT NULL, role TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS projects(user_id INTEGER NOT NULL REFERENCES users(id),
          name TEXT NOT NULL, content TEXT NOT NULL, kind TEXT NOT NULL,
          PRIMARY KEY(user_id,name,kind));
        ''')


def user():
    if 'uid' not in session:
        return None
    with db() as conn:
        row = conn.execute('SELECT * FROM users WHERE id=?', (session['uid'],)).fetchone()
    return row if row and row['revision'] == session.get('revision') else None


def protected(teacher=False):
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            current = user()
            if not current:
                abort(401)
            if teacher and current['role'] != 'teacher':
                abort(403)
            return function(current, *args, **kwargs)
        return wrapped
    return decorate


@app.before_request
def csrf():
    if request.method in ('POST', 'PUT', 'DELETE'):
        token = request.headers.get('X-CSRF-Token') or request.form.get('csrf')
        if not token or not secrets.compare_digest(token, session.get('csrf', '')):
            abort(403)


@app.after_request
def headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
    return response


@app.errorhandler(400)
@app.errorhandler(401)
@app.errorhandler(403)
@app.errorhandler(413)
def error(exc):
    return jsonify(ok=False, error=exc.description), exc.code


@app.get('/health')
def health():
    return jsonify(ok=True, version=VERSION)


@app.route('/', methods=['GET'])
def index():
    session.setdefault('csrf', secrets.token_hex(24))
    current = user()
    return render_template('index.html' if current else 'login.html', current=current, version=VERSION)


@app.post('/login')
def login():
    address = request.remote_addr
    now = time.monotonic()
    recent = [t for t in FAILURES.get(address, []) if now - t < 300]
    if len(recent) >= 15:
        return 'Too many attempts. Wait five minutes.', 429
    name = request.form.get('name', '').lower()
    with db() as conn:
        current = conn.execute('SELECT * FROM users WHERE name=?', (name,)).fetchone()
    if not current or not check_password_hash(current['password'], request.form.get('password', '')):
        FAILURES[address] = recent + [now]
        return render_template('login.html', error='Incorrect username or password.'), 401
    session.clear()
    session.update(uid=current['id'], revision=current['revision'], csrf=secrets.token_hex(24))
    session.permanent = True
    return redirect('/')


def runner(current, action, **data):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(35)
        conn.connect(os.environ.get('CN_SOCKET', '/run/codynick-server/runner.sock'))
        conn.sendall((json.dumps(dict(uid=current['id'], action=action, **data)) + '\n').encode())
        with conn.makefile() as file:
            return json.loads(file.readline(2000000))


@app.post('/api/logout')
@protected()
def logout(current):
    try:
        runner(current, 'stop')
    finally:
        session.clear()
    return jsonify(ok=True)


@app.route('/api/run/<action>', methods=['GET', 'POST'])
@protected()
def execution(current, action):
    if action not in ('run', 'stop', 'status', 'input') or (request.method == 'GET' and action != 'status'):
        abort(400)
    values = request.get_json(silent=True) or {}
    try:
        if action == 'run':
            result = runner(current, action, code=values.get('code', ''))
        elif action == 'input':
            result = runner(current, action, values=values)
        else:
            result = runner(current, action)
        return jsonify(result), 200 if result.get('ok') else 400
    except (OSError, ValueError) as exc:
        app.logger.exception('Runner unavailable')
        return jsonify(ok=False, error='Execution service unavailable. Contact the teacher.'), 503


@app.route('/api/projects', methods=['GET', 'POST', 'DELETE'])
@protected()
def projects(current):
    kind = request.args.get('kind', 'python')
    if kind not in ('python', 'blocks'):
        abort(400)
    with db() as conn:
        if request.method == 'GET':
            rows = conn.execute('SELECT name,content FROM projects WHERE user_id=? AND kind=? ORDER BY name',
                                (current['id'], kind)).fetchall()
            return jsonify(ok=True, projects=[dict(row) for row in rows])
        data = request.get_json()
        name = data.get('name', '').strip()
        if not re.fullmatch(r'[\w .-]{1,80}', name) or name.startswith('.'):
            abort(400, 'Use a name of 1-80 letters, numbers, spaces, dots or hyphens.')
        if request.method == 'DELETE':
            conn.execute('DELETE FROM projects WHERE user_id=? AND name=? AND kind=?', (current['id'], name, kind))
        else:
            content = data.get('content', '')
            if not isinstance(content, str) or len(content.encode()) > 65536:
                abort(400, 'Each project must be at most 64 KB.')
            conn.execute('BEGIN IMMEDIATE')
            existing = conn.execute('SELECT 1 FROM projects WHERE user_id=? AND name=? AND kind=?', (current['id'], name, kind)).fetchone()
            if existing and not data.get('overwrite'):
                return jsonify(ok=False, error='Project already exists.', conflict=True), 409
            count = conn.execute('SELECT COUNT(*) FROM projects WHERE user_id=?', (current['id'],)).fetchone()[0]
            if not existing and count >= 100:
                abort(400, 'The 100-project quota has been reached.')
            conn.execute('INSERT INTO projects VALUES(?,?,?,?) ON CONFLICT(user_id,name,kind) DO UPDATE SET content=excluded.content',
                         (current['id'], name, content, kind))
    return jsonify(ok=True)


@app.route('/api/students', methods=['GET', 'POST'])
@protected(teacher=True)
def students(current):
    with db() as conn:
        if request.method == 'GET':
            rows = conn.execute("SELECT id,name FROM users WHERE role='student' ORDER BY name").fetchall()
            return jsonify(ok=True, students=[dict(row) for row in rows])
        data = request.get_json()
        name, password = data.get('name', '').lower(), data.get('password', '')
        if not re.fullmatch('[a-z][a-z0-9_-]{2,31}', name) or not 10 <= len(password) <= 128:
            abort(400, 'Username: 3-32 lowercase characters. Password: 10-128 characters.')
        hashed = generate_password_hash(password)
        if data.get('reset'):
            row = conn.execute("SELECT id FROM users WHERE name=? AND role='student'", (name,)).fetchone()
            if not row:
                abort(400, 'Student not found.')
            runner(dict(id=row['id']), 'stop')
            conn.execute("UPDATE users SET password=?,revision=revision+1 WHERE id=?", (hashed, row['id']))
        else:
            if conn.execute('SELECT COUNT(*) FROM users').fetchone()[0] >= 101:
                abort(400, 'Account limit reached.')
            try:
                conn.execute("INSERT INTO users(name,password,role) VALUES(?,?,'student')", (name, hashed))
            except sqlite3.IntegrityError:
                abort(400, 'Username already exists.')
    return jsonify(ok=True)


initialize()
