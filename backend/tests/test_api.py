"""Application tests without PostgreSQL; integration smoke tests are separate."""
import os
os.environ.setdefault('SECRET_KEY','test-secret-'*5)
os.environ.setdefault('POSTGRES_PASSWORD','test-password-'*3)
os.environ.setdefault('ADMIN_PASSWORD','test-admin-password-123')
from fastapi.testclient import TestClient
from app import main, config, state
import pytest

@pytest.fixture
def client(tmp_path,monkeypatch):
 monkeypatch.setattr(config,'STATE',tmp_path/'state.sqlite')
 monkeypatch.setattr(main.pg,'init_template',lambda:None)
 with TestClient(main.app) as c: yield c

def test_auth_csrf_and_ownership(client):
 assert client.get('/api/databases').status_code==401
 assert client.post('/api/login',json={'username':'teacher','password':'test-admin-password-123'}).status_code==403
 h={'X-Lab-Request':'1'}
 assert client.post('/api/login',headers=h,json={'username':'teacher','password':'wrong'}).status_code==401
 assert client.post('/api/login',headers=h,json={'username':'teacher','password':'test-admin-password-123'}).status_code==200
 assert 'HttpOnly' in client.cookies.__repr__() or client.cookies.get('lab_session')
 assert client.post('/api/databases/other/query',headers=h,json={'sql':'SELECT 1'}).status_code==404
 assert client.post('/api/databases/other/query',headers=h,json={'sql':'SELECT 1','database':'postgres'}).status_code==422
 assert client.post('/api/logout',headers=h).status_code==200
 assert client.get('/api/me').status_code==401

def test_upload_limit(client,monkeypatch):
 monkeypatch.setattr(config,'UPLOAD',1024)
 r=client.post('/api/login',headers={'X-Lab-Request':'1'},content=b'x'*1025)
 assert r.status_code==413

def test_password_hash():
 hashed=state.password_hash('correct-password')
 assert state.password_ok('correct-password',hashed)
 assert not state.password_ok('wrong-password',hashed)


def test_anonymous_workspace_and_teacher_switch(client,monkeypatch):
 monkeypatch.setattr(main.pg,'make_database',lambda uid:'lab_'+uid)
 h={'X-Lab-Request':'1'}
 first=client.post('/api/guest',headers=h)
 assert first.status_code==200
 guest=first.json()
 assert guest['guest']==1 and guest['admin']==0
 assert 'HttpOnly' in first.headers['set-cookie']
 assert client.post('/api/guest',headers=h).json()['id']==guest['id']
 assert len(client.get('/api/databases').json())==1
 assert client.get('/api/admin/users').status_code==403
 assert client.post('/api/password',headers=h,json={'password':'not-needed-password'}).status_code==403
 assert client.post('/api/login',headers=h,json={'username':'teacher','password':'test-admin-password-123'}).status_code==200
 assert client.get('/api/me').json()['admin']==1
 client.post('/api/logout',headers=h)
 assert client.get('/api/me').json()['id']==guest['id']

def test_guest_quota_and_cross_browser_isolation(client,monkeypatch):
 monkeypatch.setattr(main.pg,'make_database',lambda uid:'lab_'+uid)
 monkeypatch.setattr(config,'MAX_USERS',3)
 h={'X-Lab-Request':'1'}
 one=client.post('/api/guest',headers=h).json()
 did=client.get('/api/databases').json()[0]['id']
 with TestClient(main.app) as other:
  two=other.post('/api/guest',headers=h).json()
  assert two['id']!=one['id']
  assert other.post('/api/databases/'+did+'/query',headers=h,json={'sql':'SELECT 1'}).status_code==404
 with TestClient(main.app) as third:
  assert third.post('/api/guest',headers=h).status_code==503
