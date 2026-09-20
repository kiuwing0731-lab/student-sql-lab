"""Run inside backend container: verifies actual PostgreSQL role boundaries."""
import secrets
from app import database as pg
from psycopg import sql, Error
uid=secrets.token_hex(16); other=secrets.token_hex(16)
databases=[]
try:
 a=pg.make_database(uid); databases.append(a)
 b=pg.make_database(other); databases.append(b)
 for target in ('postgres','school_template',b):
  try:
   with pg.connect(target,uid): pass
  except Error: pass
  else: raise AssertionError('Cross-database connection allowed: '+target)
 for source in ('CREATE ROLE forbidden SUPERUSER','CREATE DATABASE forbidden',
                'ALTER ROLE '+pg.role(uid)+' SUPERUSER',
                "COPY students TO PROGRAM 'true'",
                "SELECT pg_read_file('/etc/passwd')",
                "SELECT set_config('statement_timeout','0',false)"):
  try:
   with pg.connect(a,uid) as c: c.execute(source)
  except Error: pass
  else: raise AssertionError('Role boundary failed: '+source)
 with pg.connect(a,uid) as c:
  assert c.execute('SELECT count(*) FROM students').fetchone()[0]==6
 print('PASS: actual student role cannot connect to other databases or gain server/file/program privileges.')
finally:
 for name in databases: pg.drop_database(name)
 with pg.connect(autocommit=True) as c:
  for u in (uid,other): c.execute(sql.SQL('DROP ROLE IF EXISTS {}').format(sql.Identifier(pg.role(u))))
