FROM python:3.12-slim

WORKDIR /app

# Install system dependencies including ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN cp uvicorn_runner.py /usr/local/bin/uvicorn && chmod +x /usr/local/bin/uvicorn

ENV PORT=8000
EXPOSE 8000

CMD ["python", "main.py"]
