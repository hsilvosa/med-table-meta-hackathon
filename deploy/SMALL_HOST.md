# Running the online demo on a 512 MB host (Render, Koyeb, Fly.io)

The same `Dockerfile` runs on any Docker host. Set the environment variable `PORT=7860` if the host asks for a port.

Memory use, measured with `docker run --memory 512m --memory-swap 512m` (no OOM kill):

- Idle: about 90 MB.
- One planner session, up to the Check screen, and 4 simultaneous live scans of 48 MP photos: peak 438 MB.
- 4 simultaneous live scans of 12 MP photos with the phone effects: peak 250 MB.

What keeps it under the limit (online demo only, `PUBLIC_DEMO=1`):

- glibc malloc settings in the `Dockerfile` (`MALLOC_ARENA_MAX`, `MALLOC_MMAP_THRESHOLD_`, `MALLOC_TRIM_THRESHOLD_`) return freed photo memory to the system.
- A photo of more than 16 MP is decoded at half size (48 MP becomes 12 MP) before anything else (`shrink` in `scripts/serve_world.py`).
- One live scan at a time, and two decoder threads instead of four.

Free plans of these hosts have a very small CPU share (about 0.1 vCPU). A live scan that takes 2 s on a PC can take much longer there.
