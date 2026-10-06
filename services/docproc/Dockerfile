FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_ROOT=/data/storage \
    DOCPROC_PORT=8102

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY docproc ./docproc

RUN mkdir -p /data/storage/raw /data/storage/processed

EXPOSE 8102

CMD ["uvicorn", "docproc.api:app", "--host", "0.0.0.0", "--port", "8102"]
