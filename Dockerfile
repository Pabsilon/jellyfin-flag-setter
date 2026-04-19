FROM python:3.14-alpine

RUN apk add --no-cache imagemagick imagemagick-dev

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY jellyfin_flag_setter/ jellyfin_flag_setter/
RUN uv sync --frozen --no-dev
COPY flags/ flags/
COPY static/ static/
COPY templates/ templates/

RUN mkdir -p data

ENV MAGICK_HOME=/usr
ENV JELLYFIN_URL=""
ENV JELLYFIN_API_KEY=""
ENV SECRET_KEY=""
ENV DB_PATH="data/flagsetter.db"

EXPOSE 8000

CMD [".venv/bin/uvicorn", "jellyfin_flag_setter.main:app", "--host", "0.0.0.0", "--port", "8000"]