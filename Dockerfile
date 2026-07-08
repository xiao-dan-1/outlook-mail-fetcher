ARG PYTHON_IMAGE=python:3.11-slim
FROM ${PYTHON_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN useradd --create-home --uid 10001 --shell /usr/sbin/nologin --no-log-init appuser

COPY --chown=appuser:appuser mail_receiver ./mail_receiver

USER appuser

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/config', timeout=3).read()"]

CMD ["python", "-m", "mail_receiver.web", "--host", "0.0.0.0", "--port", "8765"]
