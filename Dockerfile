# LitReview — production image (M7).
# One container serves both the API and the frontend on $PORT (default 8000).
#
# The install is EDITABLE (-e) on purpose: app.py locates frontend/ relative
# to the repo layout (litreview/../..), so the package must run from /app,
# not from site-packages.

FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY litreview/ litreview/
COPY frontend/ frontend/
COPY data/ data/
COPY examples/ examples/

RUN pip install --no-cache-dir -e .[server]

# Non-root; /app/var is the only writable path (surveys, caches, outputs) —
# mount a volume there so surveys survive restarts and redeploys.
RUN useradd -m appuser && mkdir -p /app/var && chown -R appuser:appuser /app
USER appuser
VOLUME /app/var

# Production default: the Anthropic API backend (the file bridge needs an
# interactive Claude Code session and does not exist on a headless server).
ENV SURVEY_LLM_BACKEND=api

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s CMD \
  python -c "import os,urllib.request;urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('PORT','8000')+'/api/health',timeout=4)"

CMD ["sh", "-c", "python -m litreview.server --host 0.0.0.0 --port ${PORT:-8000} --data-dir /app/var"]
