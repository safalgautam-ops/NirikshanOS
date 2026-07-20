FROM nirikshan/base:1.0

# Basic tier — imaging, hashing, identification, metadata, and basic
# searching. dd/sha256sum/grep/find are already part of Debian's essential
# packages (coreutils/findutils/grep); python3/python3-yaml and the shared
# run_analysis.py/registry.py/loader.py/utils.py engine come from the base
# image, so only the non-essential tools need installing here.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        binutils \
        file \
        libimage-exiftool-perl \
        xxd \
        dc3dd \
 && rm -rf /var/lib/apt/lists/*

COPY modules/ /analyzer/modules/
