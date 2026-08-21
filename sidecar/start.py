"""Start official CPG privately, then the supervisor and public guard."""
from __future__ import annotations
import os, subprocess, sys

command = os.getenv("CPG_START_COMMAND", "/opt/cpg/bin/run.sh")
cpg = subprocess.Popen([command, "/opt/cpg/root/conf.yaml"])
supervisor = subprocess.Popen([sys.executable, "/opt/sidecar/supervisor.py"])
try:
    os.execv(sys.executable, [sys.executable, "/opt/sidecar/guard.py"])
finally:
    supervisor.terminate(); cpg.terminate()
