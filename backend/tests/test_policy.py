import pytest
from app.policy import validate, PolicyError

@pytest.mark.parametrize('sql',[
 'SELECT * FROM students',
 'SELECT count(*), avg(age) FROM students',
 "SELECT ';' AS semicolon /* ; */",
 'WITH x AS (SELECT 1) SELECT * FROM x',
 'CREATE TABLE books (id serial PRIMARY KEY, title text)',
 'ALTER TABLE books ADD COLUMN pages integer',
 "INSERT INTO books(title) VALUES ('hello')",
 'UPDATE books SET pages=100', 'DELETE FROM books',
 'CREATE VIEW names AS SELECT name FROM students',
 'CREATE INDEX student_name ON students(name)',
 'TRUNCATE books', 'DROP TABLE books',
])
def test_allowed(sql): assert len(validate(sql))==1

@pytest.mark.parametrize('sql',[
 'INSERT INTO pg_catalog.pg_authid VALUES (1)',
 "UPDATE pg_catalog.pg_class SET relname='evil'",
 'CREATE TABLE bad (x regrole)',
 'CREATE DATABASE victim', 'DROP DATABASE victim', 'CREATE ROLE admin SUPERUSER',
 'ALTER ROLE CURRENT_USER SUPERUSER', 'SET statement_timeout=0', 'RESET ALL',
 "SELECT set_config('statement_timeout','0',false)",
 'SELECT pg_sleep(100)', "COPY students TO PROGRAM 'id'", "COPY students FROM '/etc/passwd'",
 "DO $$BEGIN END$$", 'CREATE EXTENSION dblink', 'SELECT * FROM pg_authid',
 'SELECT * FROM pg_catalog.pg_class', 'SELECT * FROM information_schema.tables',
 'SELECT public.count(*) FROM students', "SELECT 'lab_admin'::regrole", 'BEGIN',
 'SELECT 1; DROP TABLE students', 'SELECT 1 INTO TEMP scratch',
 'CREATE TABLE t AS SELECT 1', 'ALTER TABLE students OWNER TO lab_admin',
 'GRANT ALL ON students TO PUBLIC', 'DROP SCHEMA public CASCADE',
 'SELECT * FROM dblink(\'x\',\'y\') AS t(x int)',
 "CREATE FUNCTION danger() RETURNS int LANGUAGE SQL AS 'SELECT 1'",
 "CREATE TABLE t (x text DEFAULT pg_read_file('/etc/passwd'))",
 "WITH x AS (DELETE FROM students RETURNING *) SELECT * FROM x",
 'INSERT INTO students(name) VALUES (\'x\') RETURNING *',
])
def test_rejected(sql):
 with pytest.raises(PolicyError): validate(sql)

def test_split_and_batch():
 assert len(validate("CREATE TABLE x(a text); INSERT INTO x VALUES ('a;b');",2))==2
 with pytest.raises(PolicyError): validate('-- only comments')
