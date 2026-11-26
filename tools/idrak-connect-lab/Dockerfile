FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8765 IDRAK_LAB_DATA_DIR=/data
WORKDIR /app
RUN useradd --uid 10001 --create-home lab && mkdir /data && chown lab:lab /data
COPY --chown=lab:lab demo_server.py hosted_server.py ./
COPY --chown=lab:lab public/ ./public/
USER lab
VOLUME ["/data"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8765')+'/health',timeout=2)"
CMD ["python", "hosted_server.py"]
