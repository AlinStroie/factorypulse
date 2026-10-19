# O singura imagine pentru simulator si bridge; comanda se alege in docker-compose.yml.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install . && useradd --create-home --uid 1000 factory && mkdir -p data && chown factory data

USER factory

CMD ["python", "-m", "factorypulse.simulator.server"]
