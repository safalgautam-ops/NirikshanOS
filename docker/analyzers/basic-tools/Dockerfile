FROM debian:12-slim

# Install only what the three MVP modules need.
# file       → generic.file_identification
# coreutils  → sha256sum / md5sum / sha1sum / sha512sum (generic.hash_calculation)
# binutils   → strings (generic.strings_extraction)
# python3    → entrypoint interpreter (no pip deps needed)
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        file \
        coreutils \
        binutils \
        python3 \
 && rm -rf /var/lib/apt/lists/*

# Copy entrypoint script.
COPY run_analysis.py /usr/local/bin/run-analysis
RUN chmod +x /usr/local/bin/run-analysis

# Declare mount points so Docker knows these are expected.
VOLUME ["/input", "/work", "/output"]

# docker_runner.py passes no command — this entrypoint runs automatically.
ENTRYPOINT ["python3", "/usr/local/bin/run-analysis"]
