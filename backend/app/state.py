import sqlite3, hashlib, secrets, hmac, time
from contextlib import contextmanager
from . import config as c

@contextmanager
def db():
    conn=sqlite3.connect(c.STATE,timeout=15)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback(); raise
    finally: conn.close()

def password_hash(password):
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    return salt+':'+digest

def password_ok(password, encoded):
    salt,digest=encoded.split(':')
    check=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),600000).hex()
    return hmac.compare_digest(check,digest)

def token_hash(token): return hashlib.sha256(token.encode()).hexdigest()

def initialize():
    if len(c.SECRET)<32 or len(c.PG_PASSWORD)<24 or 'CHANGE_ME' in (c.SECRET,c.PG_PASSWORD):
        raise RuntimeError('Generate .env with scripts/configure.py first.')
    c.STATE.parent.mkdir(parents=True,exist_ok=True)
    with db() as s:
        s.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, admin INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE, expires REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS databases(id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL, pg_name TEXT UNIQUE NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, at REAL NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL);
        """)
        columns={r[1] for r in s.execute('PRAGMA table_info(users)')}
        if 'guest' not in columns: s.execute('ALTER TABLE users ADD COLUMN guest INTEGER NOT NULL DEFAULT 0')
        if not s.execute('SELECT 1 FROM users WHERE admin=1').fetchone():
            password=__import__('os').environ.get('ADMIN_PASSWORD','')
            if len(password)<12 or password=='CHANGE_ME': raise RuntimeError('ADMIN_PASSWORD needs 12+ characters.')
            s.execute('INSERT INTO users(id,username,password,admin,active) VALUES(?,?,?,?,?)',(secrets.token_hex(16),__import__('os').getenv('ADMIN_USERNAME','teacher'),password_hash(password),1,1))

def audit(actor, action, target):
    with db() as s:
        s.execute('INSERT INTO audit(at,actor,action,target) VALUES(?,?,?,?)',(time.time(),actor,action,target))
        s.execute('DELETE FROM audit WHERE id < (SELECT COALESCE(MAX(id),0)-10000 FROM audit)')
