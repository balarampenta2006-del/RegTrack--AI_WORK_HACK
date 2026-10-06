# regtrack-ai service (Phase 4) - build context: services/ai
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY ai ./ai

# storage is a shared volume (PLAN.md §2.3); backend is reachable as "backend"
ENV STORAGE_ROOT=/storage \
    CHROMA_DIR=/storage/chroma \
    API_BASE=http://backend:8080 \
    LLM_MODEL=gpt-4o-mini

EXPOSE 8103

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8103/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "ai.server:app", "--host", "0.0.0.0", "--port", "8103"]
