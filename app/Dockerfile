# syntax=docker/dockerfile:1
# Build context is the repository root (see docker-compose.yml).
# Stages: base (runtime deps) -> test (adds pytest + tests) | runtime (final, default target).

FROM python@sha256:46837ed3105db0029b6d656816185c6258e3b39690532fb782428e0a5fd76182 AS base
# ^ python:3.12-slim, pinned by digest so builds are reproducible; Dependabot bumps it.

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Apply Debian security fixes released after the base image was built (e.g. zlib
# CVE-2026-85091, caught by Trivy). The digest pin keeps the starting point reproducible.
RUN apt-get update \
 && apt-get -y upgrade --no-install-recommends \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY app/requirements.txt /tmp/requirements.txt
RUN python -m pip install --no-compile -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Unprivileged runtime user: a code-execution bug does not give root in the container.
RUN groupadd --system --gid 10001 geovault \
 && useradd --system --uid 10001 --gid geovault --no-create-home --shell /usr/sbin/nologin geovault


# --- test: same base + test tooling and the test suite. Never shipped. ---------------------
FROM base AS test
COPY app/requirements.txt app/requirements-dev.txt /tmp/
RUN python -m pip install --no-compile -r /tmp/requirements-dev.txt && rm /tmp/requirements*.txt
COPY --chown=root:root pyproject.toml /srv/
COPY --chown=root:root app/ /srv/app/
COPY --chown=root:root db/migrations/ /srv/db/migrations/
COPY --chown=root:root frontend/ /srv/frontend/
COPY --chown=root:root data/ /srv/data/
COPY --chown=root:root tests/ /srv/tests/
USER 10001:10001
CMD ["pytest"]


# --- runtime: the image that actually runs. Last stage = default build target. -----------
FROM base AS runtime
COPY --chown=root:root app/ /srv/app/
COPY --chown=root:root db/migrations/ /srv/db/migrations/
COPY --chown=root:root frontend/ /srv/frontend/

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
  CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).status == 200 else 1)"]

# 0.0.0.0 inside the container is required for Docker port publishing;
# host exposure is limited by the 127.0.0.1 port mapping in docker-compose.yml.
CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
