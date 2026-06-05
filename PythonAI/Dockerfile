# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    curl \
    git \
    ffmpeg \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Expose ports for FastAPI (8765) and Streamlit (8501)
EXPOSE 8765
EXPOSE 8501

# Default command starts the API server via the CLI
CMD ["python", "-m", "src.cli", "serve", "--host", "0.0.0.0", "--port", "8765"]
