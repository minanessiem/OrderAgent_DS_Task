# Base image: Python 3.10 slim for a lightweight footprint.
FROM python:3.10-slim

# Standard Python environment variables for Docker.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Security: Create a dedicated non-root user 'appuser' to run the application.
RUN groupadd -r appuser && useradd -r -g appuser -m -d /home/appuser -s /sbin/nologin appuser

# Set the application's working directory.
WORKDIR /app

# Copy requirements first to leverage Docker's build cache for dependencies.
# If requirements.txt doesn't change, this layer won't be rebuilt.
COPY requirements.txt .

# Install Python dependencies.
# Using --no-cache-dir to keep the image size smaller.
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code, configs, and initial data.
# Note: run_experiment.py is currently not copied, uncomment if needed.
COPY src/ ./src/
COPY configs/ ./configs/
COPY data/ ./data/
# COPY run_experiment.py .

# Ensure the 'appuser' owns the application files.
RUN chown -R appuser:appuser /app

# Switch to the non-root user for running the application.
USER appuser

# Expose port 8000 for the frontend service.
# The Flask app (or whatever runs in frontend) should listen on 0.0.0.0:8000.
EXPOSE 8000

# Default command to start the application.
# This will typically run the frontend (e.g., src/frontend/app.py).
# For the mock_api_service or other services, docker-compose.yml will override this command.
# If using Hydra for the main app, the CMD might look like:
# CMD ["python", "src/frontend/app.py", "hydra.run.dir=/app/outputs/${now:%Y-%m-%d}/${now:%H-%M-%S}"]
CMD ["python", "src/frontend/app.py"]