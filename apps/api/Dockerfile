ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ARG PIP_INDEX_URL
ARG PIP_EXTRA_INDEX_URL

COPY pyproject.toml README.md ./
COPY app ./app

RUN if [ -n "$PIP_INDEX_URL" ]; then pip config set global.index-url "$PIP_INDEX_URL"; fi \
 && if [ -n "$PIP_EXTRA_INDEX_URL" ]; then pip config set global.extra-index-url "$PIP_EXTRA_INDEX_URL"; fi \
 && pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
