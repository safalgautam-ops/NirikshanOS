FROM debian:12-slim

# Tools for current modules:
#   file       → generic.file_identification
#   coreutils  → sha256sum / md5sum / sha1sum / sha512sum (generic.hash_calculation)
#   binutils   → strings                                  (generic.strings_extraction)
#   python3-yaml → YAML module definitions read by loader.py
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        file \
        coreutils \
        binutils \
        python3 \
        python3-yaml \
 && rm -rf /var/lib/apt/lists/*

# All analyzer files live here: run_analysis.py, registry.py, loader.py,
# utils.py, and the modules/ directory (YAML definitions + Python handlers).
WORKDIR /analyzer
COPY . /analyzer/

VOLUME ["/input", "/work", "/output"]

# docker_runner.py passes no command — this entrypoint reads /input/job_config.json
# and dispatches to the appropriate module handler automatically.
ENTRYPOINT ["python3", "/analyzer/run_analysis.py"]
