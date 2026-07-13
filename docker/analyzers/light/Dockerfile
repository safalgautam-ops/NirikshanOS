FROM debian:12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
        binutils \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /analyzer
COPY . /analyzer/

VOLUME ["/case", "/work", "/output"]
ENTRYPOINT ["python3", "/analyzer/run_analysis.py"]
