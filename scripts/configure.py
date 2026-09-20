#!/usr/bin/env python3
"""Generate local deployment secrets without displaying them."""
from pathlib import Path
import secrets, os
root=Path(__file__).resolve().parents[1]
target=root/'.env'
if target.exists(): raise SystemExit('.env already exists; edit it manually. Nothing overwritten.')
text=(root/'.env.example').read_text()
for key in ('POSTGRES_PASSWORD','SECRET_KEY','ADMIN_PASSWORD'):
    text=text.replace(key+'=CHANGE_ME',key+'='+secrets.token_urlsafe(36))
fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as f: f.write(text)
print('Created .env with unique secrets. Open .env to read teacher login and configure domain.')
