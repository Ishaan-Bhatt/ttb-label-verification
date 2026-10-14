FROM python:3.12-slim

# Tesseract OCR runs inside the container, so label text never leaves the server.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY samples ./samples

# One thread per Tesseract call; parallelism comes from concurrent requests,
# which is faster than letting each call fight over every core.
ENV OMP_THREAD_LIMIT=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
