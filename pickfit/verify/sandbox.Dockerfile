# Base image for verification boxes (DockerBox now, ModalBox later).
# Preinstalls what README install paths most often assume, so a box does not
# spend its command budget on setup: runtime libraries a non-root user cannot
# apt-get later (libgomp1 for llama.cpp-style binaries), download and unpack
# tools, uv/pipx for Python CLIs, and Node for npm CLIs.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bzip2 ca-certificates curl file git libgomp1 procps unzip xz-utils zstd \
 && rm -rf /var/lib/apt/lists/*

COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN pip install --no-cache-dir --disable-pip-version-check uv pipx

# The box runs as uid 1000; its home is a size-limited tmpfs mounted at run time.
RUN useradd --uid 1000 --create-home --shell /bin/bash sbx
