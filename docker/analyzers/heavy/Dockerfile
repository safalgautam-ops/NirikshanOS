FROM debian:12-slim

# Specialized Forensics tier — memory, network, Windows artifacts, mobile,
# and advanced timelines. tshark/tcpflow are plain apt packages; Volatility3,
# plaso/log2timeline and MVT are pip-only, which is exactly why loader.py's
# install: block was extended to support `pip:` alongside `apt:` - none of
# these can be apt-get installed.
#
# Not included here (need custom binary/repo work beyond apt+pip, see the
# module registration notes): Zeek (needs its own apt repo + signing key,
# not in default Debian), RegRipper and Eric Zimmerman's tools (GitHub-only
# binaries, no package). ALEAPP and iLEAPP are also excluded here — verified
# they are script-based tools with no setup.py/pyproject.toml (git-installing
# them fails: "does not appear to a Python project"), and the "aleapp"/
# "ileapp" PyPI names are unrelated reserved-name placeholder stubs with zero
# functionality, not the real tools — so both are registered as
# metadata-only modules instead of silently faked.
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
        python3-pip \
        python3-dev \
        build-essential \
        pkg-config \
        tshark \
        tcpflow \
 && rm -rf /var/lib/apt/lists/* \
 && pip3 install --no-cache-dir --break-system-packages \
        volatility3 \
        plaso \
        mvt

WORKDIR /analyzer
COPY . /analyzer/

VOLUME ["/case", "/work", "/output"]
ENTRYPOINT ["python3", "/analyzer/run_analysis.py"]
