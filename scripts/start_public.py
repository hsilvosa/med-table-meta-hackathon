"""Start the online demo inside its container: the 3D room server, the planner and nginx on the single public port 7860.

  python scripts/start_public.py        (run by the Dockerfile; PUBLIC_DEMO=1 is set there)

If any of the three stops, the others are stopped too, so the Space restarts the whole container.
"""

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
python = sys.executable
processes = [
    subprocess.Popen([python, "scripts/serve_world.py", "--port", "8600"], cwd=ROOT),
    subprocess.Popen([python, "-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1", "--server.port", "8501",
                      "--server.baseUrlPath", "app", "--server.headless", "true", "--browser.gatherUsageStats", "false",
                      "--server.fileWatcherType", "none", "--server.enableXsrfProtection", "false", "--server.enableCORS", "false"], cwd=ROOT),
    subprocess.Popen(["nginx", "-c", str(ROOT / "deploy" / "nginx.conf"), "-g", "daemon off;"], cwd=ROOT),
]
try:
    while all(p.poll() is None for p in processes):
        time.sleep(2)
finally:
    for p in processes:
        if p.poll() is None:
            p.terminate()
sys.exit(1)
