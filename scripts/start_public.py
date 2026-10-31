"""Start the online demo inside its container: the 3D room server, the planner and nginx on the single public port 7860.

  python scripts/start_public.py        (run by the Dockerfile; PUBLIC_DEMO=1 is set there)

nginx (the public port) starts only once both servers accept connections: the platform's startup check waits for it, so a first visitor
after the service has scaled to zero waits a few seconds instead of getting an error. If any process stops, the others are stopped too,
so the platform restarts the whole container.
"""

import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
python = sys.executable


def listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


processes = [
    subprocess.Popen([python, "scripts/serve_world.py", "--port", "8600"], cwd=ROOT),
    subprocess.Popen([python, "-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1", "--server.port", "8501",
                      "--server.baseUrlPath", "app", "--server.headless", "true", "--browser.gatherUsageStats", "false",
                      "--server.fileWatcherType", "none", "--server.enableXsrfProtection", "false", "--server.enableCORS", "false"], cwd=ROOT),
]
deadline = time.time() + 180
while not (listening(8600) and listening(8501)):
    if time.time() > deadline or any(p.poll() is not None for p in processes):
        for p in processes:
            p.terminate()
        sys.exit("the servers did not start")
    time.sleep(0.5)
processes.append(subprocess.Popen(["nginx", "-c", str(ROOT / "deploy" / "nginx.conf"), "-g", "daemon off;"], cwd=ROOT))
print("online demo ready on port 7860", flush=True)
try:
    while all(p.poll() is None for p in processes):
        time.sleep(2)
finally:
    for p in processes:
        if p.poll() is None:
            p.terminate()
sys.exit(1)
