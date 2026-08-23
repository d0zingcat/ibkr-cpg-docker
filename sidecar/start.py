"""Start official CPG privately, then the supervisor and public guard."""
from __future__ import annotations
import os, subprocess, sys

command = os.getenv("CPG_START_COMMAND", "/opt/cpg/bin/run.sh")
# The official ``run.sh`` uses relative ``dist`` and ``build/lib`` classpath
# entries, so it must be launched from the extracted CPG directory.
cpg_env = os.environ | {
    "JAVA_TOOL_OPTIONS": " ".join(
        part
        for part in (os.getenv("JAVA_TOOL_OPTIONS", ""), "-Dvertx.cacheDirBase=/tmp/vertx-cache")
        if part
    )
}
cpg = subprocess.Popen([command, "root/conf.yaml"], cwd="/opt/cpg", env=cpg_env)
manual_login = os.getenv("IBKR_MANUAL_LOGIN", "1") != "0"
supervisor = None if manual_login else subprocess.Popen([sys.executable, "/opt/sidecar/supervisor.py"])
try:
    os.execv(sys.executable, [sys.executable, "/opt/sidecar/guard.py"])
finally:
    if supervisor is not None:
        supervisor.terminate()
    cpg.terminate()
