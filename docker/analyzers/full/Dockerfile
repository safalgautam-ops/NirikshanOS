FROM debian:12-slim

# Enterprise tier — threat hunting and reverse engineering. capa and FLOSS
# are pip-only.
#
# Not included here (need custom binary/repo/build work well beyond apt+pip
# — see the module registration notes for why these are registered as
# metadata-only for now, not runnable): radare2 (removed from Debian's
# archives — verified no apt candidate — and its PyPI package is an
# unrelated broken stub, not the real tool; only installable via its own
# install script/repo), Velociraptor, GRR, Hayabusa, Chainsaw (GitHub-release
# binaries, no Debian package), Ghidra headless (multi-GB Java download),
# osquery (needs its own apt repo + signing key).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
        python3-pip \
        python3-dev \
        build-essential \
        git \
 && rm -rf /var/lib/apt/lists/* \
 && pip3 install --no-cache-dir --break-system-packages \
        flare-capa \
        flare-floss \
 # capa's PyPI package ships no rule content (verified: capa/rules/ only has
 # Python code) — the actual .yml rules are a separate repo it expects via -r.
 && git clone --depth 1 https://github.com/mandiant/capa-rules /opt/capa-rules \
 && rm -rf /opt/capa-rules/.git

WORKDIR /analyzer
COPY . /analyzer/

VOLUME ["/case", "/work", "/output"]
ENTRYPOINT ["python3", "/analyzer/run_analysis.py"]
