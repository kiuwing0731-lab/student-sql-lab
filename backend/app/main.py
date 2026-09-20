import csv, io, re, os, time, secrets, threading, logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, ConfigDict
import psycopg
from psycopg import sql
from . import config as c
from . import database as pg
from .state import db, initialize, password_hash, password_ok, token_hash, audit
from .policy import PolicyError

@asynccontextmanager
async def lifespan(app):
    initialize(); pg.init_template()
    yield

app=FastAPI(title='Student SQL Lab',lifespan=lifespan,docs_url=None,redoc_url=None)

class BodyLimit:
    def __init__(self,app): self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http': return await self.app(scope,receive,send)
        if scope['method'] not in ('GET','HEAD','OPTIONS'):
            headers=dict(scope['headers'])
            if headers.get(b'x-lab-request')!=b'1':
                return await JSONResponse({'detail':'Missing same-origin request header.'},403)(scope,receive,send)
            data=bytearray()
            while True:
                msg=await receive()
                if msg['type']=='http.disconnect': return
                data.extend(msg.get('body',b''))
                if len(data)>c.UPLOAD:
                    return await JSONResponse({'detail':'Upload too large.'},413)(scope,receive,send)
                if not msg.get('more_body'): break
            consumed=False
            async def buffered():
                nonlocal consumed
                if consumed: return await receive()
                consumed=True
                return {'type':'http.request','body':bytes(data),'more_body':False}
            return await self.app(scope,buffered,send)
        return await self.app(scope,receive,send)
app.add_middleware(BodyLimit)

@app.exception_handler(PolicyError)
async def policy_error(request,exc): return JSONResponse({'detail':str(exc)},400)
@app.exception_handler(psycopg.Error)
async def sql_error(request,exc):
    # Do not expose DSNs, connection credentials or infrastructure errors.
    message=exc.diag.message_primary or 'Database temporarily unavailable.'
    return JSONResponse({'detail':message,'sqlstate':exc.sqlstate},400 if exc.sqlstate else 503)

class Model(BaseModel): model_config=ConfigDict(extra='forbid')
class Login(Model):
    username: str=Field(min_length=1,max_length=64)
    password: str=Field(min_length=1,max_length=256)
class UserCreate(Login): pass
class Password(Model): password: str=Field(min_length=12,max_length=256)
class Active(Model): active: bool
class DatabaseCreate(Model): name: str=Field(min_length=1,max_length=60)
class Query(Model): sql: str=Field(min_length=1,max_length=100000)

DUMMY=password_hash('not-a-valid-user-password')
attempts={}; attempt_lock=threading.Lock()
def session_user(token):
    if not token: return None
    with db() as s:
        row=s.execute('SELECT u.* FROM users u JOIN sessions x ON x.user_id=u.id WHERE x.token=? AND x.expires>? AND u.active=1',(token_hash(token),time.time())).fetchone()
    return dict(row) if row else None

def user(request:Request):
    who=session_user(request.cookies.get('lab_session','')) or session_user(request.cookies.get('lab_guest',''))
    if not who: raise HTTPException(401,'Your practice session expired. Reload to start a new workspace.')
    return who
def admin(who=Depends(user)):
    if not who['admin']: raise HTTPException(403,'Teacher access required.')
    return who

def public_user(who): return {k:who[k] for k in ('id','username','admin','active','guest')}

@app.get('/api/health')
def health(): return {'status':'ok'}

@app.post('/api/login')
def login(body:Login,response:Response):
    now=time.time()
    with attempt_lock:
        for key in list(attempts):
            if attempts[key][0]<now-300: del attempts[key]
        if len(attempts)>=2000 and body.username not in attempts: raise HTTPException(429,'Try again later.')
        since,count=attempts.get(body.username,(now,0))
        if count>=10: raise HTTPException(429,'Too many attempts; wait five minutes.')
        attempts[body.username]=(since,count+1)
    with db() as s:
        who=s.execute('SELECT * FROM users WHERE username=?',(body.username,)).fetchone()
        valid=password_ok(body.password,who['password'] if who else DUMMY)
        if not valid or not who or not who['active'] or who['guest']: raise HTTPException(401,'Invalid username or password.')
        token=secrets.token_urlsafe(32)
        s.execute('DELETE FROM sessions WHERE expires<? OR user_id=?',(now,who['id']))
        s.execute('INSERT INTO sessions VALUES(?,?,?)',(token_hash(token),who['id'],now+28800))
    with attempt_lock: attempts.pop(body.username,None)
    response.set_cookie('lab_session',token,httponly=True,secure=c.SECURE,samesite='strict',max_age=28800,path='/')
    return public_user(who)

@app.post('/api/logout')
def logout(request:Request,response:Response):
    with db() as s: s.execute('DELETE FROM sessions WHERE token=?',(token_hash(request.cookies.get('lab_session','')),))
    response.delete_cookie('lab_session',path='/'); return {'ok':True}

@app.get('/api/me')
def me(who=Depends(user)): return public_user(who)

@app.post('/api/password')
def change_password(body:Password,who=Depends(user)):
    if who['guest']: raise HTTPException(403,'Guest workspaces do not use passwords.')
    with db() as s:
        s.execute('UPDATE users SET password=? WHERE id=?',(password_hash(body.password),who['id']))
        s.execute('DELETE FROM sessions WHERE user_id=?',(who['id'],))
    return {'ok':True}

@app.get('/api/databases')
def databases(who=Depends(user)):
    with db() as s: return [dict(r) for r in s.execute('SELECT id,name FROM databases WHERE user_id=? ORDER BY name',(who['id'],))]

def create_database(uid,name):
    with pg.provision_lock:
        with db() as s:
            if s.execute('SELECT count(*) FROM databases WHERE user_id=?',(uid,)).fetchone()[0]>=c.MAX_DATABASES: raise HTTPException(409,'Student database limit reached.')
            if s.execute('SELECT count(*) FROM databases').fetchone()[0]>=c.MAX_TOTAL: raise HTTPException(409,'Classroom database limit reached.')
        name_pg=pg.make_database(uid); did=secrets.token_hex(16)
        try:
            with db() as s: s.execute('INSERT INTO databases VALUES(?,?,?,?)',(did,uid,name,name_pg))
        except BaseException:
            pg.drop_database(name_pg); raise
        return {'id':did,'name':name}

@app.post('/api/databases',status_code=201)
def new_database(body:DatabaseCreate,who=Depends(user)):
    with pg.exclusive(who['id']): result=create_database(who['id'],body.name)
    audit(who['id'],'clone',result['id']); return result

@app.post('/api/databases/{did}/reset')
def reset(did:str,who=Depends(user)):
    return reset_for(who['id'],did,who['id'])

def reset_for(uid,did,actor):
    with pg.exclusive(uid),pg.provision_lock:
        old=pg.owned(uid,did)
        new=pg.make_database(uid)
        try:
            with db() as s: s.execute('UPDATE databases SET pg_name=? WHERE id=?',(new,did))
        except BaseException:
            pg.drop_database(new); raise
        # A crash after the metadata switch is repaired by startup garbage collection.
        pg.drop_database(old['pg_name'])
    audit(actor,'reset',did); return {'ok':True}

@app.delete('/api/databases/{did}')
def delete(did:str,who=Depends(user)):
    with pg.exclusive(who['id']),pg.provision_lock:
        old=pg.owned(who['id'],did)
        with db() as s: s.execute('DELETE FROM databases WHERE id=?',(did,))
        pg.drop_database(old['pg_name'])
    audit(who['id'],'delete_database',did); return {'ok':True}

@app.post('/api/databases/{did}/query')
def query(did:str,body:Query,who=Depends(user)):
    with pg.exclusive(who['id']):
        target=pg.owned(who['id'],did)
        return pg.run(who['id'],target['pg_name'],body.sql)

@app.post('/api/databases/{did}/import/sql')
async def import_sql(did:str,request:Request,who=Depends(user)):
    raw=await request.body()
    try: source=raw.decode('utf-8-sig')
    except UnicodeError: raise HTTPException(400,'Use a UTF-8 .sql file.')
    # Offload all blocking database work; requests remain responsive while SQL runs.
    from starlette.concurrency import run_in_threadpool
    def work():
        with pg.exclusive(who['id']):
            target=pg.owned(who['id'],did)
            result=pg.run(who['id'],target['pg_name'],source,multiple=True)
        audit(who['id'],'import_sql',did); return result
    return await run_in_threadpool(work)

@app.post('/api/databases/{did}/import/csv')
async def import_csv(did:str,request:Request,table:str,who=Depends(user)):
    if not re.fullmatch(r'[a-z][a-z0-9_]{0,47}',table) or table.startswith(('pg_','sql_')):
        raise HTTPException(400,'Table name: lowercase letters, digits and underscores, starting with a letter.')
    raw=await request.body()
    try: text=raw.decode('utf-8-sig')
    except UnicodeError: raise HTTPException(400,'Use a UTF-8 CSV file.')
    from starlette.concurrency import run_in_threadpool
    def work():
        reader=csv.reader(io.StringIO(text),strict=True)
        try:
            columns=next(reader)
            if not 1<=len(columns)<=100 or len(set(columns))!=len(columns) or any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,62}',x) for x in columns):
                raise HTTPException(400,'CSV needs 1–100 unique column names using letters, digits and underscores.')
            with pg.exclusive(who['id']):
                target=pg.owned(who['id'],did)
                with pg.practice(who['id'],target['pg_name']) as conn:
                    conn.execute(sql.SQL('CREATE TABLE public.{} ({})').format(sql.Identifier(table),sql.SQL(',').join(sql.SQL('{} text').format(sql.Identifier(x)) for x in columns)))
                    count=0; start=time.monotonic()
                    with conn.cursor().copy(sql.SQL('COPY public.{} ({}) FROM STDIN').format(sql.Identifier(table),sql.SQL(',').join(map(sql.Identifier,columns)))) as copy:
                        for row in reader:
                            count+=1
                            if len(row)!=len(columns): raise HTTPException(400,f'CSV row {count+1}: incorrect number of fields; import rolled back.')
                            if count>50000: raise HTTPException(400,'CSV maximum is 50,000 rows.')
                            if time.monotonic()-start>c.TIMEOUT: raise HTTPException(408,'CSV time limit; rolled back.')
                            copy.write_row(row)
            audit(who['id'],'import_csv',did)
            return {'rows_imported':count,'table':table}
        except (csv.Error,StopIteration) as exc: raise HTTPException(400,'Malformed or empty CSV.') from exc
    return await run_in_threadpool(work)

@app.get('/api/admin/users')
def users(who=Depends(admin)):
    with db() as s:
        return [dict(r) for r in s.execute('SELECT u.id,u.username,u.admin,u.active,u.guest,count(d.id) AS databases FROM users u LEFT JOIN databases d ON d.user_id=u.id GROUP BY u.id ORDER BY u.username')]

@app.post('/api/admin/users',status_code=201)
def add_user(body:UserCreate,who=Depends(admin)):
    if not re.fullmatch(r'[A-Za-z0-9_.-]{1,64}',body.username) or len(body.password)<12:
        raise HTTPException(400,'Username uses letters/digits/._-; password needs 12+ characters.')
    with pg.provision_lock:
        uid=secrets.token_hex(16)
        with db() as s:
            if s.execute('SELECT count(*) FROM users').fetchone()[0]>=c.MAX_USERS: raise HTTPException(409,'User limit reached.')
            if s.execute('SELECT 1 FROM users WHERE username=?',(body.username,)).fetchone(): raise HTTPException(409,'Username already exists.')
            s.execute('INSERT INTO users(id,username,password,admin,active) VALUES(?,?,?,?,?)',(uid,body.username,password_hash(body.password),0,1))
        try: create_database(uid,'School DB')
        except BaseException:
            with db() as s: s.execute('DELETE FROM users WHERE id=?',(uid,))
            with pg.connect(autocommit=True) as conn: conn.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(pg.role(uid))))
            raise
    audit(who['id'],'create_user',uid); return {'id':uid,'username':body.username}

@app.patch('/api/admin/users/{uid}')
def set_active(uid:str,body:Active,who=Depends(admin)):
    if uid==who['id']: raise HTTPException(400,'Cannot disable your own account.')
    with pg.exclusive(uid),db() as s:
        if not s.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone(): raise HTTPException(404,'User not found.')
        s.execute('UPDATE users SET active=? WHERE id=?',(int(body.active),uid))
        s.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
    audit(who['id'],'set_active',uid); return {'ok':True}

@app.post('/api/admin/users/{uid}/password')
def teacher_password(uid:str,body:Password,who=Depends(admin)):
    with db() as s:
        if not s.execute('SELECT 1 FROM users WHERE id=?',(uid,)).fetchone(): raise HTTPException(404,'User not found.')
        s.execute('UPDATE users SET password=? WHERE id=?',(password_hash(body.password),uid))
        s.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
    audit(who['id'],'password_reset',uid); return {'ok':True}

@app.get('/api/admin/users/{uid}/databases')
def student_databases(uid:str,who=Depends(admin)):
    with db() as s: return [dict(r) for r in s.execute('SELECT id,name FROM databases WHERE user_id=?',(uid,))]

@app.post('/api/admin/users/{uid}/databases/{did}/reset')
def teacher_reset(uid:str,did:str,who=Depends(admin)): return reset_for(uid,did,who['id'])

@app.get('/api/admin/audit')
def audit_log(who=Depends(admin)):
    with db() as s: return [dict(r) for r in s.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 100')]


@app.post('/api/guest')
def guest(request:Request,response:Response):
    existing=session_user(request.cookies.get('lab_guest',''))
    if existing and existing['guest']:
        return public_user(existing)
    # Quotas + serialized provisioning prevent concurrent visitors bypassing limits.
    with pg.provision_lock:
        with db() as s:
            if s.execute('SELECT count(*) FROM users').fetchone()[0]>=c.MAX_USERS:
                raise HTTPException(503,'All practice spaces are in use. Ask the teacher to remove old guest workspaces.')
            if s.execute('SELECT count(*) FROM databases').fetchone()[0]>=c.MAX_TOTAL:
                raise HTTPException(503,'Classroom database limit reached. Please try again later.')
        uid=secrets.token_hex(16)
        with db() as s:
            s.execute('INSERT INTO users(id,username,password,admin,active,guest) VALUES(?,?,?,?,?,1)',(uid,'guest_'+uid[:12],password_hash(secrets.token_urlsafe(32)),0,1))
        try: create_database(uid,'School DB')
        except BaseException:
            with db() as s: s.execute('DELETE FROM users WHERE id=?',(uid,))
            with pg.connect(autocommit=True) as conn: conn.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(pg.role(uid))))
            raise
        token=secrets.token_urlsafe(32); now=time.time()
        with db() as s:
            s.execute('INSERT INTO sessions VALUES(?,?,?)',(token_hash(token),uid,now+30*86400))
            result=dict(s.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone())
    response.set_cookie('lab_guest',token,httponly=True,secure=c.SECURE,samesite='strict',max_age=30*86400,path='/')
    audit(uid,'guest_created',uid)
    return public_user(result)

@app.delete('/api/admin/users/{uid}')
def remove_user(uid:str,who=Depends(admin)):
    if uid==who['id']: raise HTTPException(400,'Cannot delete your own teacher account.')
    with pg.exclusive(uid),pg.provision_lock:
        with db() as s:
            row=s.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            if not row: raise HTTPException(404,'User not found.')
            names=[r[0] for r in s.execute('SELECT pg_name FROM databases WHERE user_id=?',(uid,))]
            s.execute('DELETE FROM databases WHERE user_id=?',(uid,))
            s.execute('DELETE FROM users WHERE id=?',(uid,))
        for name in names: pg.drop_database(name)
        with pg.connect(autocommit=True) as conn:
            conn.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(pg.role(uid))))
    audit(who['id'],'delete_user',uid)
    return {'ok':True}
