# The online demo (Hugging Face Space): one public port, nginx in front of the 3D room server and the Streamlit planner.
#   docker build -t med-table . && docker run --rm -p 7860:7860 med-table      -> http://127.0.0.1:7860
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends nginx && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user PATH=/home/user/.local/bin:$PATH PUBLIC_DEMO=1 PYTHONUNBUFFERED=1 \
    MALLOC_ARENA_MAX=2 MALLOC_MMAP_THRESHOLD_=131072 MALLOC_TRIM_THRESHOLD_=131072
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
COPY --chown=user . .
RUN python scripts/fetch_web_deps.py

EXPOSE 7860
CMD ["python", "scripts/start_public.py"]
