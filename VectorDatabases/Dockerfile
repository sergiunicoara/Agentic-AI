# Use a lightweight Python base
FROM python:3.10-slim

# Set the working directory
WORKDIR /app

# Install system dependencies required for FAISS and other libraries
RUN apt-get update && apt-get install -y \
    build-essential \
    libopenblas-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install them
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Expose Gradio's default port
EXPOSE 7860

# Set environment variables for Gradio to run in a container
ENV GRADIO_SERVER_NAME="0.0.0.0"

# Run the application
CMD ["python", "app.py"]