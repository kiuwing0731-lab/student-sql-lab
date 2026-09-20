import os
from pathlib import Path

def number(name, default, low, high):
    value=int(os.getenv(name,str(default)))
    if not low<=value<=high: raise RuntimeError(f'{name} must be {low}..{high}')
    return value
SECRET=os.environ.get('SECRET_KEY','')
PG_PASSWORD=os.environ.get('POSTGRES_PASSWORD','')
STATE=Path(os.getenv('STATE_PATH','/data/platform.sqlite'))
TIMEOUT=number('QUERY_TIMEOUT_SECONDS',10,1,30)
MAX_ROWS=number('MAX_ROWS',500,1,2000)
UPLOAD=number('MAX_UPLOAD_BYTES',5242880,1024,5242880)
STATEMENTS=number('MAX_SQL_STATEMENTS',100,1,200)
RESULT_BYTES=number('MAX_RESULT_BYTES',1048576,1024,2097152)
MAX_USERS=number('MAX_USERS',100,1,1000)
MAX_DATABASES=number('MAX_DATABASES',2,1,5)
MAX_TOTAL=number('MAX_TOTAL_DATABASES',200,1,1000)
CONNECTIONS=number('STUDENT_CONNECTION_LIMIT',2,1,3)
ACTIVE=number('MAX_ACTIVE_QUERIES',12,1,20)
SECURE=os.getenv('COOKIE_SECURE','false').lower()=='true'
