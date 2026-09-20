#!/usr/bin/env python3
"""Consistent backup: pauses API writes, snapshots PostgreSQL and account metadata."""
from pathlib import Path
from datetime import datetime, timezone
import subprocess, shutil, os
root=Path(__file__).resolve().parents[1]
os.chdir(root)
out=root/'backups'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
out.mkdir(parents=True,mode=0o700)
def run(*args,**kwargs): return subprocess.run(['docker','compose',*args],check=True,**kwargs)
run('stop','backend')
try:
 with (out/'cluster.sql').open('wb') as f:
  run('exec','-T','postgres','pg_dumpall','-U','lab_admin',stdout=f)
 run('run','--rm','--no-deps','backend','python','-c',"import sqlite3; a=sqlite3.connect('/data/platform.sqlite'); b=sqlite3.connect('/data/snapshot.sqlite'); a.backup(b); b.close(); a.close()")
 run('cp','backend:/data/snapshot.sqlite',str(out/'platform.sqlite'))
 shutil.copyfile('.env',out/'.env')
 for p in out.iterdir(): p.chmod(0o600)
 print('Backup saved:',out)
finally: run('start','backend')
