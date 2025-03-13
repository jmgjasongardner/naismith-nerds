# Stage 1: Builder
FROM python:3.11.0 AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Create a virtual environment and install requirements
RUN python -m venv .venv
COPY requirements.txt ./  # Ensure this has Flask listed
RUN .venv/bin/pip install -r requirements.txt

# Stage 2: Final image
FROM python:3.11.0-slim
WORKDIR /app

# Copy the virtual environment and application files
COPY --from=builder /app/.venv .venv/
COPY . .  # This copies all your application code (including flask_app)

# Set the virtual environment path as an environment variable
ENV PATH="/app/.venv/bin:$PATH"

# Run the Flask application
CMD ["flask", "run", "--host=0.0.0.0", "--port=8080"]
