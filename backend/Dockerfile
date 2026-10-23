FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN groupadd --system --gid 10001 cyberpme && useradd --system --uid 10001 --gid cyberpme cyberpme
COPY pyproject.toml ./
RUN pip install --no-cache-dir .
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker-entrypoint.sh ./
RUN chmod +x /app/docker-entrypoint.sh
USER 10001:10001
EXPOSE 8000
CMD ["/app/docker-entrypoint.sh"]
