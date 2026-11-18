FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml ./
COPY radar ./radar
RUN pip install .

COPY eval ./eval

RUN useradd --create-home radar
USER radar

EXPOSE 8000
# Render/Fly inyectan $PORT; por defecto 8000
CMD ["sh", "-c", "uvicorn radar.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
