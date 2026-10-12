FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data LOG_DIR=/app/logs CACHE_DIR=/app/cache LAB_USER_DIR=/app/user \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd --gid 10001 lab && useradd --uid 10001 --gid lab --no-create-home lab
COPY --chown=lab:lab . /app
RUN mkdir -p /app/logs /app/cache /app/user && chown lab:lab /app/logs /app/cache /app/user
USER lab
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://'+os.environ.get('STREAMLIT_SERVER_ADDRESS','127.0.0.1').replace('0.0.0.0','127.0.0.1')+':8501/_stcore/health',timeout=4)" || exit 1
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.headless=true", "--server.enableCORS=false", "--server.enableXsrfProtection=false", "--browser.gatherUsageStats=false"]
