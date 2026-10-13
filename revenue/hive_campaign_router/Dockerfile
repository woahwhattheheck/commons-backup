FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ROUTEFOUNDRY_DB=/data/routefoundry.db \
    PORT=8080

WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 routefoundry \
    && mkdir -p /data \
    && chown routefoundry:routefoundry /data
COPY --chown=routefoundry:routefoundry . ./

USER routefoundry
VOLUME ["/data"]
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8080')+'/health', timeout=2).read()"
CMD ["python", "app.py", "--host", "0.0.0.0"]
