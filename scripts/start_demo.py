"""Start the whole demo: the 3D room (port 8600) with the caregiver app (port 8501) embedded in its side panel.

  .venv-app/Scripts/python.exe scripts/start_demo.py [--no-browser]

Uses the room built on this machine (web/world) or, in a fresh clone, the small room shipped in web/world_demo; fetches three.js
once if needed (network).
Ctrl+C stops both servers. Both bind to 127.0.0.1 only. Open the room page; the planner is its right-hand panel (Tab).
"""

import argparse
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--no-browser", action="store_true")
args = ap.parse_args()
python = sys.executable

if not Path("web/vendor/three.module.js").exists():
    subprocess.run([python, "scripts/fetch_web_deps.py"], check=True)
if not Path("web/world/world.json").exists() and not Path("web/world_demo/world.json").exists():
    subprocess.run([python, "scripts/build_world.py"], check=True)

servers = [
    subprocess.Popen([python, "scripts/serve_world.py", "--port", "8600"]),
    subprocess.Popen([python, "-m", "streamlit", "run", "app.py", "--server.address", "127.0.0.1", "--server.port", "8501",
                      "--server.headless", "true", "--browser.gatherUsageStats", "false"]),
]
try:
    time.sleep(4)
    print("\n3D room:  http://127.0.0.1:8600\nApp:      http://127.0.0.1:8501\n"
          "Walk to a table, press 'Phone over the table', hold still for the green boxes, then 'Take photo': the planner on the right loads it.\n"
          "Ctrl+C to stop.", flush=True)
    if not args.no_browser:
        webbrowser.open("http://127.0.0.1:8600")
        webbrowser.open("http://127.0.0.1:8501")
    for server in servers:
        server.wait()
except KeyboardInterrupt:
    pass
finally:
    for server in servers:
        server.terminate()
