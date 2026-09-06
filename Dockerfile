# StaticPulse — AI-assisted PR security reviewer, packaged with Semgrep so it
# runs anywhere (including Windows hosts) with no local Python/Semgrep setup.
FROM python:3.11-slim

# git is needed for diff-scoping; nothing else.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the package + Semgrep. Copy only what's needed to build the wheel so
# the layer caches well.
COPY pyproject.toml README.md ./
COPY staticpulse ./staticpulse
RUN pip install --no-cache-dir . semgrep \
    && semgrep --version

COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# The container works on the mounted repo.
WORKDIR /src
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["--help"]
