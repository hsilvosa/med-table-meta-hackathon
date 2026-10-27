"""Start the camera demo: the camera page (port 8700) and the caregiver planner (port 8501), which the page shows in its side panel.

  .venv-app/Scripts/python.exe scripts/start_camera.py [--no-browser] [--lan] [--https]

Both servers listen on 127.0.0.1 only, so the camera of THIS computer can be used (a webcam). For a phone on the same Wi-Fi add --lan --https: both then listen
on the local network (anyone on it could reach them: use it at home and stop it when done), the camera page uses a self-signed certificate (the phone's
browser warns once), and the planner, which has no https, opens in its own tab. Ctrl+C stops both.
"""

import argparse
import socket
import subprocess
import sys
import time
import webbrowser

ap = argparse.ArgumentParser()
ap.add_argument("--no-browser", action="store_true")
ap.add_argument("--lan", action="store_true", help="listen on the local network, for a phone")
ap.add_argument("--https", action="store_true", help="https with a self-signed certificate (a phone needs it for the camera)")
args = ap.parse_args()
python = sys.executable


def lan_address() -> str:
    """The address of this computer on the local network (no data is sent: connecting a UDP socket only picks the route)."""
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


host = "0.0.0.0" if args.lan else "127.0.0.1"
camera = [python, "scripts/serve_camera.py", "--port", "8700"] + (["--lan"] if args.lan else []) + (["--https"] if args.https else [])
planner = [python, "-m", "streamlit", "run", "app.py", "--server.address", host, "--server.port", "8501", "--server.headless", "true", "--browser.gatherUsageStats", "false"]
servers = [subprocess.Popen(camera), subprocess.Popen(planner)]
try:
    time.sleep(4)
    scheme = "https" if args.https else "http"
    shown = lan_address() if args.lan else "127.0.0.1"
    print(f"\nCamera page: {scheme}://{shown}:8700/camera.html\nPlanner:     http://{shown}:8501/?source=camera\n"
          "Press 'Start the camera', point it at the boxes, hold still: green boxes mark the codes that are read. Take photo sends it to the planner.\n"
          "Ctrl+C to stop.", flush=True)
    if args.lan:
        print("WARNING: the servers listen on the local network. Use it at home and stop them when you are done.", flush=True)
    if not args.no_browser:
        webbrowser.open("http://127.0.0.1:8700/camera.html" if not args.https else f"https://127.0.0.1:8700/camera.html")
    for server in servers:
        server.wait()
except KeyboardInterrupt:
    pass
finally:
    for server in servers:
        server.terminate()
