import getpass
import secrets
from app import db, generate_password_hash, initialize

initialize()
with db() as conn:
    if not conn.execute("SELECT 1 FROM users WHERE role='teacher'").fetchone():
        password = secrets.token_urlsafe(15)
        conn.execute("INSERT INTO users(name,password,role) VALUES('teacher',?,'teacher')",
                     (generate_password_hash(password),))
        print('Teacher username: teacher\nInitial password: ' + password)
    else:
        print('Existing teacher account preserved.')
