# Visual Task Factory: the whole pipeline in one image. Only Docker is needed to run it.
#   docker build -t visual-task-factory .
#   docker run --rm -e OPENROUTER_API_KEY -v "$(pwd)/out:/out" visual-task-factory <command>
# The API key is passed at run time only. Nothing secret is copied in (see .dockerignore).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.12 /uv /usr/local/bin/uv

# Same rendering everywhere: headless matplotlib, fixed hash seed, no bytecode timestamps in outputs.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH=/opt/venv/bin:$PATH \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/matplotlib \
    PYTHONHASHSEED=0 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Dependencies first (pinned by uv.lock), so code changes don't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Everything a run produces goes to /out (mount a host folder there), including the response cache.
ENV OUT_DIR=/out \
    EVAL_CACHE_DIR=/out/cache
VOLUME /out

ENTRYPOINT ["python", "-m", "factory"]
CMD ["--help"]
