# Base image for verification boxes (DockerBox now, ModalBox later).
# Preinstalls what README install paths most often assume, so a box does not
# spend its command budget on setup: runtime libraries a non-root user cannot
# apt-get later (libgomp1 for llama.cpp-style binaries), download and unpack
# tools, uv/pipx for Python CLIs, and Node for npm CLIs. iproute2 lets the
# harness (as root, before the agent starts) route cloud metadata to nowhere.
# slirp4netns is a gVisor box's network uplink: the box user's own network
# namespace reaches out only through it, so the network cut can close DNS too.
# libicu: .NET aborts without it (exit 134), and nearly every desktop Linux has it;
# its package name carries the ICU version, so it is looked up.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      bzip2 ca-certificates curl file git iproute2 libgomp1 procps slirp4netns unzip xz-utils zstd \
      $(apt-cache pkgnames libicu | grep -E '^libicu[0-9]+$') \
 && rm -rf /var/lib/apt/lists/*

COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

RUN pip install --no-cache-dir --disable-pip-version-check uv pipx

# What pickfit/sbom.py runs in a replay box before it closes, to list what was installed (licenses in NOTICE). Each
# is its project's own release, checked against a pinned SHA-256 before it is unpacked: syft 1.56.0 (Apache-2.0) and
# cargo-audit 0.22.2 (Apache-2.0 OR MIT). govulncheck 1.9.0 (BSD-3-Clause) has no release binary: it is built here
# with Go 1.27.4 (the build box's pin, linux_box.GO_SHA256; sum.golang.org checks the module), then Go is removed,
# since -mode=binary needs no toolchain. The last line fails the build when one of them does not run.
RUN curl -fsSL -o /tmp/syft.tgz https://github.com/anchore/syft/releases/download/v1.56.0/syft_1.56.0_linux_amd64.tar.gz \
 && echo '1c2493cfcf52d3367d6cb25780d9190c111c2219c34c820574c43e8bae15c528  /tmp/syft.tgz' | sha256sum -c - \
 && mkdir /tmp/syft && tar -xzf /tmp/syft.tgz -C /tmp/syft \
 && install -m 0755 "$(find /tmp/syft -type f -name syft | head -n 1)" /usr/local/bin/syft \
 && curl -fsSL -o /tmp/cargo-audit.tgz https://github.com/rustsec/rustsec/releases/download/cargo-audit/v0.22.2/cargo-audit-x86_64-unknown-linux-musl-v0.22.2.tgz \
 && echo '7fb9497f8594b389e5fce5ef9b92db08432996895b2e0c5a0167a69ed445c428  /tmp/cargo-audit.tgz' | sha256sum -c - \
 && mkdir /tmp/cargo-audit && tar -xzf /tmp/cargo-audit.tgz -C /tmp/cargo-audit \
 && install -m 0755 "$(find /tmp/cargo-audit -type f -name cargo-audit | head -n 1)" /usr/local/bin/cargo-audit \
 && curl -fsSL -o /tmp/go.tgz https://go.dev/dl/go1.27.4.linux-amd64.tar.gz \
 && echo '7226736c2339719cda28fbf3a54d71aa63bcefe376e98cef00034268dab24840  /tmp/go.tgz' | sha256sum -c - \
 && tar -xzf /tmp/go.tgz -C /tmp \
 && GOBIN=/usr/local/bin GOPATH=/tmp/gopath GOCACHE=/tmp/gocache GOTOOLCHAIN=local CGO_ENABLED=0 \
      /tmp/go/bin/go install golang.org/x/vuln/cmd/govulncheck@v1.9.0 \
 && rm -rf /tmp/syft /tmp/syft.tgz /tmp/cargo-audit /tmp/cargo-audit.tgz /tmp/go /tmp/go.tgz /tmp/gopath /tmp/gocache \
 && syft version && cargo-audit --version && govulncheck -version

# The box runs as uid 1000; its home is a size-limited tmpfs mounted at run time.
RUN useradd --uid 1000 --create-home --shell /bin/bash sbx
