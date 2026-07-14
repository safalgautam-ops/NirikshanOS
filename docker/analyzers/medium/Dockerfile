FROM debian:12-slim

# Core Forensics tier — file-system analysis, recovery, carving, and basic
# timelines (all plain apt packages, no pip needed).
#
# Not included here: bulk_extractor is not packaged in Debian or Ubuntu's
# default archives (verified — no candidate in either), only obtainable via
# a source build or third-party PPA, so it is registered as a metadata-only
# module for now rather than silently faked.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
        sleuthkit \
        foremost \
        scalpel \
 && rm -rf /var/lib/apt/lists/* \
 # scalpel's default config ships every file-type rule commented out — it
 # would otherwise refuse to carve anything at all (verified: "configuration
 # file didn't specify any file types to carve"). Enable the common ones.
 && sed -i -E 's/^#(\s*(jpg|gif|png|pdf|zip)\s)/\1/' /etc/scalpel/scalpel.conf

WORKDIR /analyzer
COPY . /analyzer/

VOLUME ["/case", "/work", "/output"]
ENTRYPOINT ["python3", "/analyzer/run_analysis.py"]
