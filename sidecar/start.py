"""Start official CPG privately, then the data guard and private control API."""
from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

# ``start.py`` is executed by path in the image, so include /opt (the parent
# of the ``sidecar`` package) before importing sibling package modules.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from sidecar.control import serve

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
control = serve()
try:
    # Do not exec the guard: ``os.execv`` replaces this interpreter and kills
    # the control server's daemon thread, leaving port 8081 unavailable.
    guard = subprocess.Popen([sys.executable, "/opt/sidecar/guard.py"])
    guard.wait()
finally:
    control.shutdown()
    cpg.terminate()
