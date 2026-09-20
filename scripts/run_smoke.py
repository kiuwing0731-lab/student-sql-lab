#!/usr/bin/env python3
from pathlib import Path
import os, subprocess, sys
root=Path(__file__).resolve().parents[1]
for line in (root/'.env').read_text().splitlines():
 if line and not line.startswith('#') and '=' in line:
  key,value=line.split('=',1); os.environ.setdefault(key,value)
subprocess.run([sys.executable,str(root/'scripts/smoke.py')],check=True)
