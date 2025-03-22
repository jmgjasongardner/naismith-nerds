# Stage 1: Builder
FROM python:3.11.0 AS builder

# Set environment variables to avoid creating .pyc files and buffering
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Set the working directory to the root of the project
WORKDIR /naismith-nerds

# Create a virtual environment and install requirements
RUN python -m venv .venv
COPY requirements.txt .
RUN .venv/bin/pip install -r requirements.txt

# Stage 2: Final image
FROM python:3.11.0-slim

# Set the working directory to the flask_app directory where app.py is
WORKDIR /naismith-nerds/flask_app

# Copy the virtual environment and application files
COPY --from=builder /naismith-nerds/.venv /naismith-nerds/.venv
COPY . .

# Set the virtual environment path as an environment variable
ENV PATH="/naismith-nerds/.venv/bin:$PATH"

# Set the FLASK_APP environment variable to point to your app.py
ENV FLASK_APP=flask_app.app.py

# Run the Flask application
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
