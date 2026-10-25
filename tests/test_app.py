import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TEMP = tempfile.TemporaryDirectory()
os.environ['CN_DATA'] = TEMP.name
os.environ['CN_SECRET'] = 'test-only-secret'
sys.path.insert(0, str(ROOT / 'server'))
import app as module


class ClassroomTests(unittest.TestCase):
    def setUp(self):
        with module.db() as conn:
            conn.execute('DELETE FROM projects')
            conn.execute('DELETE FROM users')
            for name, role in [('teacher', 'teacher'), ('student1', 'student'), ('student2', 'student')]:
                conn.execute('INSERT INTO users(name,password,role) VALUES(?,?,?)',
                             (name, module.generate_password_hash('classroom-test-password'), role))
        self.teacher = self.login('teacher')
        self.first = self.login('student1')
        self.second = self.login('student2')

    def login(self, name):
        client = module.app.test_client()
        client.get('/')
        with client.session_transaction() as session:
            token = session['csrf']
        response = client.post('/login', data=dict(name=name, password='classroom-test-password', csrf=token))
        self.assertEqual(response.status_code, 302)
        return client

    def post(self, client, url, values, method='POST'):
        with client.session_transaction() as session:
            token = session['csrf']
        return client.open(url, method=method, json=values, headers={'X-CSRF-Token': token})

    def test_private_projects_and_delete(self):
        self.assertEqual(self.post(self.first, '/api/projects', dict(name='Private', content='print(1)')).status_code, 200)
        self.assertEqual(len(self.first.get('/api/projects').json['projects']), 1)
        self.assertEqual(self.second.get('/api/projects').json['projects'], [])
        self.post(self.second, '/api/projects', dict(name='Private'), method='DELETE')
        self.assertEqual(len(self.first.get('/api/projects').json['projects']), 1)

    def test_overwrite_confirmation(self):
        data = dict(name='Demo', content='print(1)')
        self.post(self.first, '/api/projects', data)
        self.assertEqual(self.post(self.first, '/api/projects', data).status_code, 409)
        data['overwrite'] = True
        self.assertEqual(self.post(self.first, '/api/projects', data).status_code, 200)

    def test_student_cannot_manage_accounts(self):
        self.assertEqual(self.first.get('/api/students').status_code, 403)
        self.assertEqual(self.post(self.first, '/api/students', dict(name='hacker', password='long-password')).status_code, 403)

    @patch('app.runner', return_value={'ok': True})
    def test_short_password_creation_reset_and_login(self, mock):
        self.assertEqual(self.post(self.teacher, '/api/students', dict(name='shortpass', password='a')).status_code, 200)
        self.assertEqual(self.post(self.teacher, '/api/students', dict(name='student1', password='b', reset=True)).status_code, 200)
        for name, password in [('shortpass', 'a'), ('student1', 'b')]:
            client = module.app.test_client()
            client.get('/')
            with client.session_transaction() as session:
                token = session['csrf']
            self.assertEqual(client.post('/login', data=dict(name=name, password=password, csrf=token)).status_code, 302)
        self.assertEqual(self.post(self.teacher, '/api/students', dict(name='empty', password='')).status_code, 400)
        self.assertEqual(self.post(self.teacher, '/api/students', dict(name='toolong', password='a' * 129)).status_code, 400)

    @patch('app.runner', return_value={'ok': True})
    def test_teacher_reset_invalidates_session(self, mock):
        response = self.post(self.teacher, '/api/students', dict(name='student1', password='new-password-123', reset=True))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.first.get('/api/projects').status_code, 401)
        self.assertEqual(self.second.get('/api/projects').status_code, 200)

    def test_csrf_and_authentication(self):
        self.assertEqual(self.first.post('/api/run/stop', json={}).status_code, 403)
        self.assertEqual(module.app.test_client().get('/api/projects').status_code, 401)

    def test_limits_and_name_validation(self):
        self.assertEqual(self.post(self.first, '/api/projects', dict(name='../bad', content='')).status_code, 400)
        self.assertEqual(self.post(self.first, '/api/projects', dict(name='Big', content='x' * 65537)).status_code, 400)

    @patch('app.runner', return_value={'ok': True})
    def test_runner_identity_is_from_session(self, mock):
        self.post(self.first, '/api/run/run', dict(uid=999, code='print(1)'))
        self.assertEqual(mock.call_args.args[0]['name'], 'student1')
        self.assertEqual(mock.call_args.kwargs, dict(code='print(1)'))

    @patch('app.runner')
    def test_templates(self, mock):
        import base64
        mock.return_value = dict(ok=True, body=base64.b64encode(b'<html><head></head><body>Block Coding</body></html>').decode())
        response = self.first.get('/')
        self.assertIn(b'Block Coding', response.data)
        self.assertIn(b'server-session.js', response.data)
        self.assertNotIn(b'id="student-form"', response.data)
        self.assertEqual(self.first.get('/account/students').status_code, 403)
        self.assertIn(b'id="student-form"', self.teacher.get('/account/students').data)

    @patch('app.runner')
    def test_tool_identity_and_role(self, mock):
        import base64
        mock.return_value = dict(ok=True, body=base64.b64encode(b'<head></head>').decode())
        self.first.get('/code/')
        self.assertEqual(mock.call_args.args[0]['name'], 'student1')
        self.assertEqual(mock.call_args.kwargs['role'], 'student')
        self.assertEqual(self.first.get('/teachers/').status_code, 403)


if __name__ == '__main__':
    unittest.main()
