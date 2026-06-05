# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (required for massive data scraping, video/audio)
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    git \
    ffmpeg \
    awscli \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirement files first to leverage Docker cache
COPY requirements.txt .
COPY requirements_god_mode.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -r requirements_god_mode.txt

# Copy the rest of the application
COPY . .

# Make port 8000 available to the world outside this container (for any web UI)
EXPOSE 8000

# Run collect_everything.py as the default command when container starts
CMD ["python", "collect_everything.py", "--phase", "all"]
