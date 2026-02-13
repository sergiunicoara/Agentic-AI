# Base image
FROM python:3.10-slim

# Prevent Python from buffering output and writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set working directory
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Ensure CV file exists inside the container
COPY app/cv.txt /app/app/cv.txt

# Port for Cloud Run / Uvicorn
ENV PORT=8080

# Start app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]