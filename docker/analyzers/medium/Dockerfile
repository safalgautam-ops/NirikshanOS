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
 && rm -rf /var/lib/apt/lists/*

WORKDIR /analyzer
COPY . /analyzer/

VOLUME ["/case", "/work", "/output"]
ENTRYPOINT ["python3", "/analyzer/run_analysis.py"]
