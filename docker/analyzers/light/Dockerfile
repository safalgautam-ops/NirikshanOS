FROM debian:12-slim

# Basic tier — imaging, hashing, identification, metadata, and basic
# searching. dd/sha256sum/grep/find are already part of Debian's essential
# packages (coreutils/findutils/grep), so only the non-essential tools need
# installing here.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
        binutils \
        file \
        libimage-exiftool-perl \
        xxd \
        dc3dd \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /analyzer
COPY . /analyzer/

VOLUME ["/case", "/work", "/output"]
ENTRYPOINT ["python3", "/analyzer/run_analysis.py"]
