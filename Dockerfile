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

# State (DuckDB, prebuilt artifacts, any uploaded workbook) lives here. With no
# Fly volume attached this is the machine's own filesystem: it survives restarts
# and suspends, but is replaced on deploy, after which artifacts rebuild on
# first boot. Point NN_DATA_DIR at a mount if a volume is ever added.
ENV NN_DATA_DIR=/naismith-nerds/data
RUN mkdir -p /naismith-nerds/data

EXPOSE 8080

# One worker: the dataset is held in memory and swapped in place, so a second
# worker would double the memory and refresh the data twice.
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8080", \
     "--timeout", "120", "--graceful-timeout", "30", \
     "flask_app.app:app"]
