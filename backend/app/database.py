import os, secrets, hashlib, hmac, threading, time, json
from contextlib import contextmanager
from pathlib import Path
import psycopg
from psycopg import sql
from fastapi import HTTPException
from . import config as c
from .state import db
from .policy import validate

# Single application process; locks intentionally cover run/import/reset/delete.
provision_lock=threading.RLock()
lock_guard=threading.Lock()
user_locks={}
slots=threading.BoundedSemaphore(c.ACTIVE)

def role(uid): return 'u_'+uid

def credential(uid): return hmac.new(c.SECRET.encode(),uid.encode(),hashlib.sha256).hexdigest()

def connect(database='postgres', uid=None, autocommit=False):
    return psycopg.connect(host=os.getenv('DATABASE_HOST','postgres'),port=int(os.getenv('DATABASE_PORT','5432')),
        dbname=database,user=role(uid) if uid else 'lab_admin',password=credential(uid) if uid else c.PG_PASSWORD,
        connect_timeout=5,autocommit=autocommit,options=f'-c statement_timeout={c.TIMEOUT*1000 if uid else 30000} -c lock_timeout=3000')

@contextmanager
def exclusive(uid):
    with lock_guard: lock=user_locks.setdefault(uid,threading.Lock())
    if not lock.acquire(blocking=False): raise HTTPException(409,'Another operation is running for this student.')
    try: yield
    finally: lock.release()

def init_template():
    with connect(autocommit=True) as conn:
        # Reapply cluster isolation on every start; excludes template0 (already non-connectable).
        for name, in conn.execute('SELECT datname FROM pg_database WHERE datallowconn'):
            conn.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(name)))
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname='school_template'").fetchone():
            conn.execute('CREATE DATABASE school_template TEMPLATE template0')
            try:
                with connect('school_template') as seed:
                    seed.execute('REVOKE ALL ON SCHEMA public FROM PUBLIC')
                    seed.execute(Path(__file__).with_name('school.sql').read_text(),prepare=False)
                conn.execute('ALTER DATABASE school_template ALLOW_CONNECTIONS false')
            except BaseException:
                conn.execute('DROP DATABASE school_template WITH (FORCE)'); raise
        conn.execute('REVOKE ALL ON DATABASE school_template FROM PUBLIC')
        conn.execute('ALTER DATABASE school_template ALLOW_CONNECTIONS false')
    # Garbage-collect crash leftovers only in our generated namespace.
    with db() as s:
        known={r[0] for r in s.execute('SELECT pg_name FROM databases')}
        users={r[0] for r in s.execute('SELECT id FROM users')}
    with connect(autocommit=True) as conn:
        for name, in conn.execute("SELECT datname FROM pg_database WHERE datname LIKE 'lab_%'"):
            if len(name)==36 and name.startswith('lab_') and all(x in '0123456789abcdef' for x in name[4:]) and name not in known:
                conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))
        for name, in conn.execute("SELECT rolname FROM pg_roles WHERE rolname LIKE 'u_%'"):
            if len(name)==34 and name[2:] not in users and all(x in '0123456789abcdef' for x in name[2:]):
                conn.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(name)))

def ensure_role(uid):
    with connect(autocommit=True) as conn:
        if not conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role(uid),)).fetchone():
            conn.execute(sql.SQL('CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS NOINHERIT CONNECTION LIMIT {} PASSWORD {}').format(sql.Identifier(role(uid)),sql.Literal(c.CONNECTIONS),sql.Literal(credential(uid))))
        conn.execute(sql.SQL('ALTER ROLE {} SET statement_timeout = {}').format(sql.Identifier(role(uid)),sql.Literal(str(c.TIMEOUT*1000))))
        conn.execute(sql.SQL("ALTER ROLE {} SET idle_in_transaction_session_timeout = '15s'").format(sql.Identifier(role(uid))))
        conn.execute(sql.SQL("ALTER ROLE {} SET work_mem = '4MB'").format(sql.Identifier(role(uid))))

def make_database(uid):
    ensure_role(uid)
    name='lab_'+secrets.token_hex(16)
    with connect(autocommit=True) as conn:
        conn.execute(sql.SQL('CREATE DATABASE {} TEMPLATE school_template CONNECTION LIMIT {}').format(sql.Identifier(name),sql.Literal(c.CONNECTIONS)))
        try:
            conn.execute(sql.SQL('REVOKE ALL ON DATABASE {} FROM PUBLIC').format(sql.Identifier(name)))
            conn.execute(sql.SQL('GRANT CONNECT ON DATABASE {} TO {}').format(sql.Identifier(name),sql.Identifier(role(uid))))
            with connect(name) as target:
                target.execute(sql.SQL('ALTER SCHEMA public OWNER TO {}').format(sql.Identifier(role(uid))))
                for table in ('students','courses','enrollments'):
                    target.execute(sql.SQL('ALTER TABLE {} OWNER TO {}').format(sql.Identifier(table),sql.Identifier(role(uid))))
                # Defense in depth against GUC changes via SELECT. SQL policy also denies it.
                target.execute('REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text,text,boolean) FROM PUBLIC')
            return name
        except BaseException:
            conn.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name))); raise

def drop_database(name):
    with connect(autocommit=True) as conn:
        conn.execute(sql.SQL('DROP DATABASE IF EXISTS {} WITH (FORCE)').format(sql.Identifier(name)))

def owned(uid, database_id):
    with db() as s:
        row=s.execute('SELECT * FROM databases WHERE id=? AND user_id=?',(database_id,uid)).fetchone()
    if not row: raise HTTPException(404,'Database not found.')
    return dict(row)

@contextmanager
def practice(uid,name):
    if not slots.acquire(blocking=False): raise HTTPException(429,'Classroom is busy; try again shortly.')
    try:
        with connect(name,uid) as conn:
            # Role defaults cannot be changed through the allowed SQL grammar.
            timer=threading.Timer(c.TIMEOUT,conn.cancel)
            timer.daemon=True; timer.start()
            try: yield conn
            finally: timer.cancel(); timer.join()
    finally: slots.release()

def run(uid,name,source,multiple=False):
    statements=validate(source,c.STATEMENTS if multiple else 1)
    start=time.monotonic(); results=[]
    with practice(uid,name) as conn:
        for statement in statements:
            if time.monotonic()-start>c.TIMEOUT: raise HTTPException(408,'Operation time limit exceeded; rolled back.')
            kind=json.loads(__import__('pglast').parser.parse_sql_json(statement))['stmts'][0]['stmt']
            if multiple and 'SelectStmt' in kind:
                raise HTTPException(400,'SQL import accepts DDL/DML only; run SELECT in the editor.')
            if 'SelectStmt' in kind:
                with conn.cursor(name='result') as cur:
                    cur.execute(statement)
                    columns=[x.name for x in cur.description]
                    rows=[]; size=0; truncated=False
                    for i in range(c.MAX_ROWS+1):
                        row=cur.fetchone()
                        if row is None: break
                        if i==c.MAX_ROWS: truncated=True; break
                        safe=[None if v is None else str(v) for v in row]
                        size+=len(json.dumps(safe).encode())
                        if size>c.RESULT_BYTES: truncated=True; break
                        rows.append(safe)
                    results.append({'columns':columns,'rows':rows,'truncated':truncated})
            else:
                with conn.cursor() as cur:
                    cur.execute(statement,prepare=True)
                    results.append({'columns':[],'rows':[],'status':cur.statusmessage,'truncated':False})
            if time.monotonic()-start>c.TIMEOUT: raise HTTPException(408,'Operation time limit exceeded; rolled back.')
    # Imports return summaries only; avoid accumulating many SELECT result sets.
    return {'results':results,'elapsed_ms':round((time.monotonic()-start)*1000)}
