# Stage 1: build the virtualenv
FROM python:3.11-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /naismith-nerds

RUN python -m venv .venv
COPY requirements.txt .
RUN .venv/bin/pip install --no-cache-dir -r requirements.txt

# Stage 2: runtime
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/naismith-nerds/.venv/bin:$PATH"

# The repo root is the working directory so `flask_app.app:app` and
# `collective_bball.*` resolve as top-level packages. The previous image ran
# from inside flask_app/ with the whole repo copied underneath it, which
# happened to work but made every relative path confusing.
WORKDIR /naismith-nerds

COPY --from=builder /naismith-nerds/.venv /naismith-nerds/.venv
COPY . .

# State (DuckDB, the rotating OneDrive token, prebuilt artifacts, any uploaded
# workbook) lives here. This is the Fly volume declared in fly.toml, so it
# survives deploys — which is the whole point: the token rotates on every
# refresh and the ratings history accumulates one game-day at a time, and both
# were previously wiped by each deploy.
ENV NN_DATA_DIR=/data
RUN mkdir -p /data

EXPOSE 8080

# One worker: the dataset is held in memory and swapped in place, so a second
# worker would double the memory and refresh the data twice.
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", \
     "--timeout", "120", "--graceful-timeout", "30", \
     "flask_app.app:app"]
