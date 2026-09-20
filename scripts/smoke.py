#!/usr/bin/env python3
"""End-to-end checks against a running deployment. Creates 2 named test users."""
import json, os, time, uuid, urllib.request, urllib.error, http.cookiejar
BASE=os.getenv('LAB_URL','http://localhost:8080').rstrip('/')
class Client:
 def __init__(self): self.http=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def call(self,path,method='GET',body=None,expected=200,raw=False):
  time.sleep(0.15) # Stay below the production reverse-proxy rate limit.
  headers={'X-Lab-Request':'1'}
  if body is not None:
   headers['Content-Type']='application/octet-stream' if raw else 'application/json'
   body=body if raw else json.dumps(body).encode()
  req=urllib.request.Request(BASE+'/api'+path,data=body,headers=headers,method=method)
  try:
   with self.http.open(req,timeout=40) as r: status,data=r.status,r.read()
  except urllib.error.HTTPError as e: status,data=e.code,e.read()
  assert status==expected,(path,status,data[:500])
  return json.loads(data)

def main():
 admin=Client(); a=Client(); b=Client(); password='Smoke-'+uuid.uuid4().hex
 admin.call('/login','POST',{'username':os.getenv('ADMIN_USERNAME','teacher'),'password':os.environ['ADMIN_PASSWORD']})
 users=[]
 try:
  for client in (a,b):
   u=client.call('/guest','POST'); users.append(u)
   assert client.call('/guest','POST')['id']==u['id']
  da=a.call('/databases')[0]['id']; db=b.call('/databases')[0]['id']
  def query(client,did,sql,expected=200): return client.call('/databases/'+did+'/query','POST',{'sql':sql},expected)
  assert query(a,da,'SELECT count(*) FROM students')['results'][0]['rows']==[['6']]
  query(a,db,'SELECT * FROM students',404)
  a.call('/admin/users',expected=403)
  for source in ['CREATE ROLE evil SUPERUSER',"SELECT set_config('statement_timeout','0',false)","COPY students TO PROGRAM 'id'",'SELECT * FROM pg_authid','SELECT pg_sleep(60)']:
   query(a,da,source,400)
  query(a,da,'DELETE FROM students WHERE id=6',400) # FK fails; no changes committed
  query(a,da,"UPDATE students SET name='Changed' WHERE id=1")
  assert query(b,db,'SELECT name FROM students WHERE id=1')['results'][0]['rows']==[['Alice Chan']]
  imported=b'CREATE TABLE imported(id integer, title text); INSERT INTO imported VALUES (1,\'a;b\');'
  a.call(f'/databases/{da}/import/sql','POST',imported,raw=True)
  assert query(a,da,'SELECT title FROM imported')['results'][0]['rows']==[['a;b']]
  a.call(f'/databases/{da}/import/sql','POST',b'CREATE TABLE rolledback(id int); INSERT INTO no_such_table VALUES (1);',400,True)
  query(a,da,'SELECT * FROM rolledback',400)
  a.call(f'/databases/{da}/import/csv?table=csv_data','POST',b'name,note\nAmy,"hello, world"\nBob,second\n',raw=True)
  assert query(a,da,'SELECT count(*) FROM csv_data')['results'][0]['rows']==[['2']]
  a.call(f'/databases/{da}/import/csv?table=broken_csv','POST',b'a,b\n1,2,3\n',400,True)
  query(a,da,'SELECT * FROM broken_csv',400)
  limited=query(a,da,'SELECT generate_series(1,10000)')['results'][0]
  assert limited['truncated'] and len(limited['rows'])<=2000
  clone=a.call('/databases','POST',{'name':'Second'},201)
  a.call('/databases','POST',{'name':'Over limit'},409)
  a.call('/databases/'+clone['id'],'DELETE')
  a.call('/databases/'+da+'/reset','POST')
  assert query(a,da,'SELECT name FROM students WHERE id=1')['results'][0]['rows']==[['Alice Chan']]
  query(a,da,'SELECT * FROM imported',400)
  # Expensive CPU-only query: verifies timeout without allowing pg_sleep.
  query(a,da,'SELECT count(*) FROM generate_series(1,1000000000) AS n',400)
  assert query(a,da,'SELECT 1')['results'][0]['rows']==[['1']]
  a.call('/databases/'+da+'/import/sql','POST',b'x'*5242881,413,True)
  admin.call('/admin/users/'+users[0]['id'],'PATCH',{'active':False})
  a.call('/me',expected=401)
  print('PASS: anonymous provisioning, persistent browser sessions, teacher login, RBAC, ownership, SQL policy, transactions, SQL/CSV imports, row/upload/DB limits, clone/reset, timeout and session revocation.')
 finally:
  # Teacher removes disposable guest workspaces and releases quota.
  for u in users:
   try: admin.call('/admin/users/'+u['id'],'DELETE')
   except Exception as exc: print('Cleanup requires teacher attention:',u['username'],str(exc))
if __name__=='__main__': main()
