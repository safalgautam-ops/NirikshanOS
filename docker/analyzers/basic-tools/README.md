# dfir/basic-tools:1.0

MVP analyzer image for NirikshanOS.

Supports three modules from `module_registry.py`:

| Module ID | Tool used |
|---|---|
| `generic.file_identification` | `file -b` + `file -b --mime-type` |
| `generic.hash_calculation` | `sha256sum`, `md5sum`, `sha1sum`, `sha512sum` |
| `generic.strings_extraction` | `strings -n <min_length>` |

---

## Build

```bash
cd docker/analyzers/basic-tools
docker build -t dfir/basic-tools:1.0 .
```

---

## Manual test

### 1. Create a temporary workspace

```bash
TEST_DIR=$(mktemp -d)
mkdir -p "$TEST_DIR/input" "$TEST_DIR/work" "$TEST_DIR/output/artifacts"
```

### 2. Create a sample evidence file

```bash
echo "This is a test evidence file with http://evil.example.com and 192.168.1.1" \
  > "$TEST_DIR/input/evidence"
```

### 3. Create job_config.json

```bash
cat > "$TEST_DIR/input/job_config.json" <<'EOF'
{
  "job_id": "test-job-001",
  "modules": [
    {
      "id": "generic.file_identification",
      "name": "File Identification",
      "options": {}
    },
    {
      "id": "generic.hash_calculation",
      "name": "Hash Calculation",
      "options": {
        "hash_types": ["MD5", "SHA256"]
      }
    },
    {
      "id": "generic.strings_extraction",
      "name": "Strings Extraction",
      "options": {
        "min_length": 6
      }
    }
  ]
}
EOF
```

### 4. Run the container

```bash
docker run --rm \
  --network none \
  --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=64m \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  -v "$TEST_DIR/input":/input:ro \
  -v "$TEST_DIR/work":/work:rw \
  -v "$TEST_DIR/output":/output:rw \
  dfir/basic-tools:1.0
```

### 5. Verify outputs

```bash
echo "--- result.json ---"
cat "$TEST_DIR/output/result.json"

echo "--- file identification ---"
cat "$TEST_DIR/output/generic_file_identification.txt"

echo "--- hashes ---"
cat "$TEST_DIR/output/generic_hash_calculation.txt"

echo "--- strings ---"
cat "$TEST_DIR/output/generic_strings_extraction.txt"
```

### Expected result.json

```json
{
  "job_id": "test-job-001",
  "status": "completed",
  "modules": {
    "generic.file_identification": {
      "status": "success",
      "exit_code": 0,
      "stdout_file": "generic_file_identification.txt",
      "stderr_file": "generic_file_identification.stderr.txt",
      "error": null
    },
    "generic.hash_calculation": {
      "status": "success",
      "exit_code": 0,
      "stdout_file": "generic_hash_calculation.txt",
      "stderr_file": "generic_hash_calculation.stderr.txt",
      "error": null
    },
    "generic.strings_extraction": {
      "status": "success",
      "exit_code": 0,
      "stdout_file": "generic_strings_extraction.txt",
      "stderr_file": "generic_strings_extraction.stderr.txt",
      "error": null
    }
  }
}
```

### 6. Clean up

```bash
rm -rf "$TEST_DIR"
```

---

## Security properties

- No network access (`--network none`)
- Root filesystem read-only (`--read-only`)
- All Linux capabilities dropped (`--cap-drop ALL`)
- No new privilege escalation (`--security-opt no-new-privileges`)
- `/input` mounted read-only — entrypoint cannot modify evidence
- Module IDs validated against hardcoded allowlist inside `run_analysis.py`
- All `subprocess` calls use `shell=False` with fixed argv
- Option values are validated and clamped before use — never interpolated into shell strings

---

## What comes next

1. Connect to `worker_main.py` — replace the mock sleep block with a call to `docker_runner.run_container()`
2. Add result parsing — `parser_service.parse_module_output()` reads the output files and produces structured `ParsedResult`
3. Store parsed results in DB
4. Extend with more modules (YARA, binwalk, etc.) in separate images
