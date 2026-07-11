FROM debian:12-slim

# Minimal base — only Python and apt infrastructure.
# Forensic tools are NOT pre-installed here. Each module's YAML definition
# declares which packages it needs under `install:`. The loader installs them
# at container startup (once per container lifetime), so a job that runs
# strings + file identification installs both tools inside the same container.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /analyzer
COPY . /analyzer/

VOLUME ["/case", "/work", "/output"]

# docker_runner.py passes no command — the entrypoint reads /case/job_config.json,
# installs any tools the selected modules need, runs them all in sequence,
# and writes /output/result.json.
ENTRYPOINT ["python3", "/analyzer/run_analysis.py"]
