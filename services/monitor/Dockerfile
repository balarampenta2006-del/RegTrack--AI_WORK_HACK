FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MONITOR_STORAGE_DIR=/data/snapshots

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor/ ./monitor/
RUN mkdir -p /data/snapshots

EXPOSE 8101

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8101/health')"

CMD ["uvicorn", "monitor.service:app", "--host", "0.0.0.0", "--port", "8101"]
