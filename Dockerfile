# Use Python 3.11
FROM python:3.11-slim

# Install FFmpeg (Crucial for your watermarking logic)
RUN apt-get update && apt-get install -y ffmpeg libsm6 libxext6 && apt-get clean

# Set working directory
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# Azure App Service uses port 80 by default for containers
EXPOSE 80

# Start the app
CMD ["gunicorn", "--bind", "0.0.0.0:80", "app:app"]