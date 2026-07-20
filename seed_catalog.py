"""Dev-only seed script: populates the module catalogue, the registered
analyzer instances, and the subscription plans with the real data built for
this project (22 forensics modules across 10 categories, the light/medium/
heavy/full analyzer instances, and the four subscription plans with their
per-instance access grants).

Run inside the web container (so it picks up the same DB_* env vars the app
uses):

    docker compose exec web python seed_catalog.py

Idempotent - every row is an upsert keyed on its real primary/unique key, so
running this again after a fresh migration (or to refresh an existing dev
database back to this known-good catalogue) is safe.
"""

from __future__ import annotations

import asyncio
import json

from app.config import Config
from app.core.db.orm import db
from app.core.db.pool import close_pool, init_pool
from app.core.utils.ids import new_id

CATEGORIES = [{'id': 'general',
  'name': 'General',
  'description': 'Generic file-level triage tools that apply to any evidence type - hashing, file '
                 'type ID, metadata, hex preview, strings',
  'sort_order': 0},
 {'id': 'disk_forensics',
  'name': 'Disk Forensics',
  'description': 'File-system analysis, recovery, and carving tools',
  'sort_order': 1},
 {'id': 'image_forensics',
  'name': 'Image Forensics',
  'description': 'Disk/memory image acquisition and file-image analysis tools',
  'sort_order': 2},
 {'id': 'email_forensics',
  'name': 'Email Forensics',
  'description': 'Email artifact and header analysis tools',
  'sort_order': 3},
 {'id': 'mobile_forensics',
  'name': 'Mobile Forensics',
  'description': 'Mobile device (Android/iOS) artifact extraction tools',
  'sort_order': 4},
 {'id': 'static_analysis',
  'name': 'Static Analysis (Reverse Engineering)',
  'description': 'Binary/malware reverse engineering tools',
  'sort_order': 5},
 {'id': 'network_forensics',
  'name': 'Network Forensics',
  'description': 'Packet capture and network traffic analysis tools',
  'sort_order': 6},
 {'id': 'windows_artifacts',
  'name': 'Windows Artifacts',
  'description': 'Registry, event log, and Windows-specific artifact analysis tools',
  'sort_order': 7},
 {'id': 'threat_hunting_edr',
  'name': 'Threat Hunting & EDR',
  'description': 'Remote endpoint forensics, EDR, and fast triage/hunting tools',
  'sort_order': 8},
 {'id': 'memory_forensics',
  'name': 'Memory Forensics',
  'description': 'Memory dump analysis tools',
  'sort_order': 9}]

INSTANCES = [{'id': 'full',
  'display_name': 'Full',
  'image_tag': 'nirikshan/full:1.0',
  'cpu_limit': '8.0',
  'memory_limit': '16g',
  'pids_limit': 1024,
  'queue_name': 'full_queue',
  'default_timeout_seconds': 600,
  'is_active': 1},
 {'id': 'heavy',
  'display_name': 'Heavy',
  'image_tag': 'nirikshan/heavy:1.0',
  'cpu_limit': '4.0',
  'memory_limit': '4g',
  'pids_limit': 512,
  'queue_name': 'heavy_queue',
  'default_timeout_seconds': 600,
  'is_active': 1},
 {'id': 'light',
  'display_name': 'Light',
  'image_tag': 'nirikshan/light:1.0',
  'cpu_limit': '1.0',
  'memory_limit': '512m',
  'pids_limit': 128,
  'queue_name': 'light_queue',
  'default_timeout_seconds': 120,
  'is_active': 1},
 {'id': 'medium',
  'display_name': 'Medium',
  'image_tag': 'nirikshan/medium:1.0',
  'cpu_limit': '2.0',
  'memory_limit': '1g',
  'pids_limit': 256,
  'queue_name': 'medium_queue',
  'default_timeout_seconds': 300,
  'is_active': 1}]

PLANS = [{'id': 'free',
  'display_name': 'Free',
  'description': 'Basic forensic triage for individuals and evaluation.',
  'price_monthly': '0.00',
  'price_annual': '0.00',
  'resources': {'vcpu': 2, 'ram_gb': 2, 'storage_gb': 20},
  'allowed_tiers': ['basic'],
  'is_active': 1,
  'sort_order': 0},
 {'id': 'basic',
  'display_name': 'Basic',
  'description': 'Essential forensic tools for small teams.',
  'price_monthly': '999.00',
  'price_annual': '11111.00',
  'resources': {'vcpu': 4, 'ram_gb': 8, 'storage_gb': 100},
  'allowed_tiers': ['basic', 'core_forensics'],
  'is_active': 1,
  'sort_order': 1},
 {'id': 'pro',
  'display_name': 'Pro',
  'description': 'Full forensic suite for professional investigators.',
  'price_monthly': '1499.00',
  'price_annual': '17777.00',
  'resources': {'vcpu': 8, 'ram_gb': 32, 'storage_gb': 500},
  'allowed_tiers': ['basic', 'core_forensics', 'specialized_forensics'],
  'is_active': 1,
  'sort_order': 2},
 {'id': 'enterprise',
  'display_name': 'Enterprise',
  'description': 'Unlimited access with dedicated resources for large teams.',
  'price_monthly': '1999.00',
  'price_annual': '23333.00',
  'resources': {'vcpu': 32, 'ram_gb': 128, 'storage_gb': 2000},
  'allowed_tiers': ['basic', 'core_forensics', 'specialized_forensics', 'enterprise'],
  'is_active': 1,
  'sort_order': 3}]

PLAN_INSTANCES = [{'plan_id': 'basic', 'instance_id': 'light'},
 {'plan_id': 'basic', 'instance_id': 'medium'},
 {'plan_id': 'enterprise', 'instance_id': 'full'},
 {'plan_id': 'enterprise', 'instance_id': 'heavy'},
 {'plan_id': 'enterprise', 'instance_id': 'light'},
 {'plan_id': 'enterprise', 'instance_id': 'medium'},
 {'plan_id': 'free', 'instance_id': 'light'},
 {'plan_id': 'pro', 'instance_id': 'heavy'},
 {'plan_id': 'pro', 'instance_id': 'light'},
 {'plan_id': 'pro', 'instance_id': 'medium'}]

MODULES = [{'id': 'disk_file_listing',
  'display_name': 'File Listing',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'disk_forensics',
  'instance_id': 'medium',
  'tier': 'core_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'disk_filesystem_info',
  'display_name': 'File System Info',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'disk_forensics',
  'instance_id': 'medium',
  'tier': 'core_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'disk_partition_layout',
  'display_name': 'Partition Layout',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'disk_forensics',
  'instance_id': 'medium',
  'tier': 'core_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'disk_file_carving',
  'display_name': 'File Carving',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'disk_forensics',
  'instance_id': 'medium',
  'tier': 'core_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'email_attachment_extractor',
  'display_name': 'Email Attachment Extractor',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'email_forensics',
  'instance_id': 'light',
  'tier': 'basic',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'email_header_parser',
  'display_name': 'Email Header Parser',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'email_forensics',
  'instance_id': 'light',
  'tier': 'basic',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'image_hash_calculation',
  'display_name': 'Hash Calculation',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'general',
  'instance_id': 'light',
  'tier': 'basic',
  'timeout_seconds': 120,
  'options_schema': [{'key': 'algorithms',
                      'type': 'list',
                      'label': 'Hash Algorithms',
                      'allowed': ['md5', 'sha1', 'sha256', 'sha512'],
                      'default': ['md5', 'sha1', 'sha256'],
                      'description': 'Which hash algorithms to compute'}],
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'image_metadata_extraction',
  'display_name': 'Metadata Extraction',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'general',
  'instance_id': 'light',
  'tier': 'basic',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'image_hex_preview',
  'display_name': 'Hex/Header Preview',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'general',
  'instance_id': 'light',
  'tier': 'basic',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'image_file_identification',
  'display_name': 'File Type Identification',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'general',
  'instance_id': 'light',
  'tier': 'basic',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'general_strings_extraction',
  'display_name': 'Strings Extraction',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'general',
  'instance_id': 'light',
  'tier': 'basic',
  'timeout_seconds': 120,
  'options_schema': [{'key': 'min_length',
                      'type': 'number',
                      'label': 'Minimum String Length',
                      'default': 4,
                      'description': 'Ignore strings shorter than this'},
                     {'key': 'include_unicode',
                      'type': 'checkbox',
                      'label': 'Include Unicode Strings',
                      'default': False,
                      'description': 'Also extract wide-char (UTF-16) strings'}],
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'general_decode_transform',
  'display_name': 'Decode/Transform',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'general',
  'instance_id': 'light',
  'tier': 'basic',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'memory_volatility_analysis',
  'display_name': 'Memory Analysis (Volatility3)',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'memory_forensics',
  'instance_id': 'heavy',
  'tier': 'specialized_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'mobile_mvt_check',
  'display_name': 'Mobile IOC Check (MVT)',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'mobile_forensics',
  'instance_id': 'heavy',
  'tier': 'specialized_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'network_conversations',
  'display_name': 'Conversations',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'network_forensics',
  'instance_id': 'heavy',
  'tier': 'specialized_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'network_protocol_hierarchy',
  'display_name': 'Protocol Hierarchy',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'network_forensics',
  'instance_id': 'heavy',
  'tier': 'specialized_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'network_stream_extraction',
  'display_name': 'Stream Extraction (tcpflow)',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'network_forensics',
  'instance_id': 'heavy',
  'tier': 'specialized_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'static_capa_capabilities',
  'display_name': 'Capability Detection (capa)',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'static_analysis',
  'instance_id': 'full',
  'tier': 'enterprise',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'static_floss_strings',
  'display_name': 'String Deobfuscation (FLOSS)',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'static_analysis',
  'instance_id': 'full',
  'tier': 'enterprise',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'hunting_yara_scan',
  'display_name': 'YARA Rule Scan',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'threat_hunting_edr',
  'instance_id': 'light',
  'tier': 'basic',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'},
 {'id': 'windows_plaso_timeline',
  'display_name': 'Timeline Generation (plaso)',
  'description': None,
  'supported_types': None,
  'parser_name': None,
  'category_id': 'windows_artifacts',
  'instance_id': 'heavy',
  'tier': 'specialized_forensics',
  'timeout_seconds': 120,
  'options_schema': None,
  'pipeline_spec': None,
  'is_enabled': 1,
  'status': 'published',
  'source': 'custom'}]

MODULE_FILES = [{'module_id': 'disk_file_carving',
  'filename': 'main.yaml',
  'content': 'id: disk_file_carving\n'
             'install:\n'
             '  apt: [foremost]\n'
             '  check: foremost\n'
             'script: |\n'
             '  import subprocess\n'
             '  from pathlib import Path\n'
             '\n'
             '  carve_dir = output_dir / "artifacts" / "carved"\n'
             '  carve_dir.parent.mkdir(parents=True, exist_ok=True)\n'
             '\n'
             '  r = subprocess.run(\n'
             '      ["foremost", "-i", "/case/evidence", "-o", str(carve_dir)],\n'
             '      capture_output=True, text=True,\n'
             '  )\n'
             '\n'
             '  audit_path = carve_dir / "audit.txt"\n'
             '  audit = audit_path.read_text() if audit_path.exists() else "(no audit.txt '
             'written)"\n'
             '  carved_files = sorted(p.name for p in carve_dir.rglob("*") if p.is_file() and '
             'p.name != "audit.txt")\n'
             '\n'
             '  stdout_path.write_text(\n'
             '      f"foremost exit code: {r.returncode}\\n"\n'
             '      f"Carved files: {carved_files}\\n\\n"\n'
             '      f"--- audit.txt ---\\n{audit}"\n'
             '  )\n'
             '  result = {\n'
             '      "status": "success" if r.returncode == 0 else "failed",\n'
             '      "exit_code": r.returncode,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": None,\n'
             '      "error": r.stderr.strip() if r.returncode != 0 else None,\n'
             '  }',
  'is_entry_point': 1},
 {'module_id': 'disk_file_listing',
  'filename': 'main.yaml',
  'content': 'id: disk_file_listing\n'
             'install:\n'
             '  apt: [sleuthkit]\n'
             '  check: fls\n'
             'argv:\n'
             '  - fls\n'
             '  - -r\n'
             '  - -p\n'
             '  - /case/evidence',
  'is_entry_point': 1},
 {'module_id': 'disk_filesystem_info',
  'filename': 'main.yaml',
  'content': 'id: disk_filesystem_info\n'
             'install:\n'
             '  apt: [sleuthkit]\n'
             '  check: fsstat\n'
             'argv:\n'
             '  - fsstat\n'
             '  - /case/evidence',
  'is_entry_point': 1},
 {'module_id': 'disk_partition_layout',
  'filename': 'main.yaml',
  'content': 'id: disk_partition_layout\n'
             'install:\n'
             '  apt: [sleuthkit]\n'
             '  check: mmls\n'
             'argv:\n'
             '  - mmls\n'
             '  - /case/evidence',
  'is_entry_point': 1},
 {'module_id': 'email_attachment_extractor',
  'filename': 'main.yaml',
  'content': 'id: email_attachment_extractor\n'
             'script: |\n'
             '  from email import policy\n'
             '  from email.parser import BytesParser\n'
             '\n'
             '  with open("/case/evidence", "rb") as f:\n'
             '      msg = BytesParser(policy=policy.default).parse(f)\n'
             '\n'
             '  lines = []\n'
             '  count = 0\n'
             '  for part in msg.walk():\n'
             '      filename = part.get_filename()\n'
             '      if filename:\n'
             '          count += 1\n'
             '          payload = part.get_payload(decode=True) or b""\n'
             '          out_path = output_dir / "artifacts" / filename\n'
             '          out_path.parent.mkdir(parents=True, exist_ok=True)\n'
             '          out_path.write_bytes(payload)\n'
             '          lines.append(f"{filename} ({len(payload)} bytes, '
             '{part.get_content_type()})")\n'
             '\n'
             '  stdout_path.write_text(f"Attachments found: {count}\\n" + "\\n".join(lines))\n'
             '  result = {\n'
             '      "status": "success",\n'
             '      "exit_code": 0,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": None,\n'
             '      "error": None,\n'
             '  }',
  'is_entry_point': 1},
 {'module_id': 'email_header_parser',
  'filename': 'main.yaml',
  'content': 'id: email_header_parser\n'
             'script: |\n'
             '  from email import policy\n'
             '  from email.parser import BytesParser\n'
             '\n'
             '  with open("/case/evidence", "rb") as f:\n'
             '      msg = BytesParser(policy=policy.default).parse(f)\n'
             '\n'
             '  fields = ["From", "To", "Cc", "Subject", "Date", "Message-ID", "Return-Path"]\n'
             '  lines = []\n'
             '  for field in fields:\n'
             '      val = msg.get(field)\n'
             '      if val:\n'
             '          lines.append(f"{field}: {val}")\n'
             '\n'
             '  received = msg.get_all("Received") or []\n'
             '  lines.append(f"\\nReceived hops: {len(received)}")\n'
             '  for i, hop in enumerate(received, 1):\n'
             '      lines.append(f"  [{i}] {hop.splitlines()[0].strip()}")\n'
             '\n'
             '  stdout_path.write_text("\\n".join(lines))\n'
             '  result = {\n'
             '      "status": "success",\n'
             '      "exit_code": 0,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": None,\n'
             '      "error": None,\n'
             '  }',
  'is_entry_point': 1},
 {'module_id': 'general_decode_transform',
  'filename': 'main.yaml',
  'content': 'id: general_decode_transform\n'
             'script: |\n'
             '  import base64\n'
             '  import codecs\n'
             '  import urllib.parse\n'
             '\n'
             '  data = Path("/case/evidence").read_bytes()\n'
             '  operation = options.get("operation", "base64_decode")\n'
             '\n'
             '  def rot13(b: bytes) -> bytes:\n'
             '      return codecs.encode(b.decode("latin-1"), "rot13").encode("latin-1")\n'
             '\n'
             '  def xor_single_byte(b: bytes, key: int) -> bytes:\n'
             '      return bytes(c ^ key for c in b)\n'
             '\n'
             '  try:\n'
             '      if operation == "base64_decode":\n'
             '          out = base64.b64decode(data, validate=False)\n'
             '      elif operation == "base64_encode":\n'
             '          out = base64.b64encode(data)\n'
             '      elif operation == "hex_decode":\n'
             '          out = bytes.fromhex(data.decode("ascii").strip())\n'
             '      elif operation == "hex_encode":\n'
             '          out = data.hex().encode("ascii")\n'
             '      elif operation == "rot13":\n'
             '          out = rot13(data)\n'
             '      elif operation == "url_decode":\n'
             '          out = urllib.parse.unquote_to_bytes(data)\n'
             '      elif operation == "url_encode":\n'
             '          out = urllib.parse.quote_from_bytes(data).encode("ascii")\n'
             '      elif operation == "xor_single_byte":\n'
             '          key = int(options.get("xor_key", 0)) & 0xFF\n'
             '          out = xor_single_byte(data, key)\n'
             '      else:\n'
             '          out = data\n'
             '\n'
             '      stdout_path.write_bytes(out[:200_000])\n'
             '      result = {\n'
             '          "status": "success",\n'
             '          "exit_code": 0,\n'
             '          "stdout_file": stdout_path.name,\n'
             '          "stderr_file": None,\n'
             '          "error": None,\n'
             '      }\n'
             '  except Exception as exc:\n'
             '      stderr_path.write_text(str(exc))\n'
             '      result = {\n'
             '          "status": "failed",\n'
             '          "exit_code": 1,\n'
             '          "stdout_file": None,\n'
             '          "stderr_file": stderr_path.name,\n'
             '          "error": f"{operation} failed: {exc}",\n'
             '      }\n'
             'options:\n'
             '  operation:\n'
             '    type: str\n'
             '    default: base64_decode\n'
             '    allowed: [base64_decode, base64_encode, hex_decode, hex_encode, rot13, '
             'url_decode, url_encode, xor_single_byte]\n'
             '    label: Operation\n'
             '    description: Simple CyberChef-style decode/encode/transform to run on the '
             'evidence bytes\n'
             '  xor_key:\n'
             '    type: int\n'
             '    default: 0\n'
             '    min: 0\n'
             '    max: 255\n'
             '    label: XOR key (0-255, only used by xor_single_byte)',
  'is_entry_point': 1},
 {'module_id': 'general_strings_extraction',
  'filename': 'main.yaml',
  'content': 'id: general_strings_extraction\n'
             'install:\n'
             '  apt: [binutils]\n'
             '  check: strings\n'
             'script: |\n'
             '  min_length = int(options.get("min_length", 4))\n'
             '  include_unicode = bool(options.get("include_unicode", False))\n'
             '\n'
             '  rc_ascii = run_cmd(["strings", "-n", str(min_length), "/case/evidence"], '
             'stdout_path, stderr_path)\n'
             '\n'
             '  combined = read_file(stdout_path)\n'
             '  if include_unicode:\n'
             '      wide_out = output_dir / "strings_wide.txt"\n'
             '      run_cmd(["strings", "-n", str(min_length), "-e", "l", "/case/evidence"], '
             'wide_out, stderr_path)\n'
             '      combined += "\\n" + read_file(wide_out)\n'
             '      stdout_path.write_text(combined)\n'
             '\n'
             '  result = {\n'
             '      "status": "success" if rc_ascii == 0 else "failed",\n'
             '      "exit_code": rc_ascii,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": stderr_path.name,\n'
             '      "error": None if rc_ascii == 0 else f"strings exited {rc_ascii}",\n'
             '  }\n'
             'options:\n'
             '  min_length:\n'
             '    type: int\n'
             '    default: 4\n'
             '    min: 3\n'
             '    max: 64\n'
             '    label: Minimum string length\n'
             '  include_unicode:\n'
             '    type: bool\n'
             '    default: false\n'
             '    label: Include Unicode (UTF-16) strings',
  'is_entry_point': 1},
 {'module_id': 'hunting_yara_scan',
  'filename': 'main.yaml',
  'content': 'id: hunting_yara_scan\n'
             'install:\n'
             '  apt: [yara]\n'
             '  check: yara\n'
             'script: |\n'
             '  from pathlib import Path\n'
             '\n'
             '  rule_text = options.get("rule_text") or (\n'
             "      'rule Suspicious_Marker_String\\n'\n"
             "      '{\\n'\n"
             "      '  strings:\\n'\n"
             '      \'    $marker = "NIRIKSHAN_TEST_STRING_MARKER_12345"\\n\'\n'
             "      '  condition:\\n'\n"
             "      '    $marker\\n'\n"
             "      '}\\n'\n"
             '  )\n'
             '  rule_path = output_dir / "scan_rules.yar"\n'
             '  rule_path.write_text(rule_text)\n'
             '\n'
             '  r = run_cmd(["yara", "-s", str(rule_path), "/case/evidence"], stdout_path, '
             'stderr_path)\n'
             '  result = {\n'
             '      "status": "success" if r == 0 else "failed",\n'
             '      "exit_code": r,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": stderr_path.name,\n'
             '      "error": None if r == 0 else f"yara exited {r} (rule compile error or bad '
             'input)",\n'
             '  }\n'
             'options:\n'
             '  rule_text:\n'
             '    type: str\n'
             '    default: ""\n'
             '    optional: true\n'
             '    label: YARA rule (blank = default marker-string rule)',
  'is_entry_point': 1},
 {'module_id': 'image_file_identification',
  'filename': 'main.yaml',
  'content': 'id: image_file_identification\n'
             'install:\n'
             '  apt: [file]\n'
             '  check: file\n'
             'argv:\n'
             '  - file\n'
             '  - --brief\n'
             '  - /case/evidence',
  'is_entry_point': 1},
 {'module_id': 'image_hash_calculation',
  'filename': 'main.yaml',
  'content': 'id: image_hash_calculation\n'
             'install:\n'
             '  apt: [coreutils]\n'
             '  check: sha256sum\n'
             'script: |\n'
             '  import subprocess\n'
             '  from pathlib import Path\n'
             '\n'
             '  evidence = Path("/case/evidence")\n'
             '  algos    = options.get("algorithms", ["md5", "sha1", "sha256"])\n'
             '\n'
             '  _hash_cmd = {\n'
             '      "md5":    ["md5sum",    str(evidence)],\n'
             '      "sha1":   ["sha1sum",   str(evidence)],\n'
             '      "sha256": ["sha256sum", str(evidence)],\n'
             '      "sha512": ["sha512sum", str(evidence)],\n'
             '  }\n'
             '\n'
             '  lines = []\n'
             '  failed = []\n'
             '  for algo in algos:\n'
             '      cmd = _hash_cmd.get(algo)\n'
             '      if not cmd:\n'
             '          continue\n'
             '      r = subprocess.run(cmd, capture_output=True, text=True)\n'
             '      if r.returncode == 0:\n'
             '          digest = r.stdout.strip().split()[0]\n'
             '          lines.append(f"{algo.upper()}: {digest}")\n'
             '      else:\n'
             '          failed.append(algo)\n'
             '          lines.append(f"{algo.upper()}: ERROR - {r.stderr.strip()}")\n'
             '\n'
             '  stdout_path.write_text("\\n".join(lines))\n'
             '  result = {\n'
             '      "status": "failed" if len(failed) == len(algos) else "success",\n'
             '      "exit_code": 1 if failed else 0,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": None,\n'
             '      "error": f"Failed algorithms: {failed}" if failed else None,\n'
             '  }\n'
             'options:\n'
             '  algorithms:\n'
             '    type: list\n'
             '    default: [md5, sha1, sha256]\n'
             '    allowed: [md5, sha1, sha256, sha512]\n'
             '    label: Hash Algorithms\n'
             '    description: Which hash algorithms to compute',
  'is_entry_point': 1},
 {'module_id': 'image_hex_preview',
  'filename': 'main.yaml',
  'content': 'id: image_hex_preview\n'
             'install:\n'
             '  apt: [xxd]\n'
             '  check: xxd\n'
             'script: |\n'
             '  from pathlib import Path\n'
             '  length = int(options.get("length", 512))\n'
             '  r = run_cmd(["xxd", "-l", str(length), "/case/evidence"], stdout_path, '
             'stderr_path)\n'
             '  result = {\n'
             '      "status": "success" if r == 0 else "failed",\n'
             '      "exit_code": r,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": stderr_path.name,\n'
             '      "error": None if r == 0 else f"xxd exited {r}",\n'
             '  }\n'
             'options:\n'
             '  length:\n'
             '    type: int\n'
             '    default: 512\n'
             '    min: 16\n'
             '    max: 65536\n'
             '    label: Bytes to preview\n'
             '    description: How many leading bytes of the evidence file to hex-dump',
  'is_entry_point': 1},
 {'module_id': 'image_metadata_extraction',
  'filename': 'main.yaml',
  'content': 'id: image_metadata_extraction\n'
             'install:\n'
             '  apt: [libimage-exiftool-perl]\n'
             '  check: exiftool\n'
             'argv:\n'
             '  - exiftool\n'
             '  - /case/evidence',
  'is_entry_point': 1},
 {'module_id': 'memory_volatility_analysis',
  'filename': 'main.yaml',
  'content': 'id: memory_volatility_analysis\n'
             'script: |\n'
             '  plugin = options.get("plugin", "windows.pslist")\n'
             '  r = run_cmd(["vol", "-q", "-f", "/case/evidence", plugin], stdout_path, '
             'stderr_path)\n'
             '  result = {\n'
             '      "status": "success" if r == 0 else "failed",\n'
             '      "exit_code": r,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": stderr_path.name,\n'
             '      "error": None if r == 0 else f"volatility3 exited {r} - see stderr (is this a '
             'supported memory image?)",\n'
             '  }\n'
             'options:\n'
             '  plugin:\n'
             '    type: str\n'
             '    default: windows.pslist\n'
             '    allowed: [windows.pslist, windows.netscan, windows.malfind, linux.pslist, '
             'linux.bash, linux.psaux]\n'
             '    label: Volatility3 plugin\n'
             '    description: Which analysis to run - Windows process list/network/injected-code, '
             'or Linux process list/bash history/process args',
  'is_entry_point': 1},
 {'module_id': 'mobile_mvt_check',
  'filename': 'main.yaml',
  'content': 'id: mobile_mvt_check\n'
             'script: |\n'
             '  from pathlib import Path\n'
             '\n'
             '  mvt_out = output_dir / "mvt_results"\n'
             '  mvt_out.mkdir(parents=True, exist_ok=True)\n'
             '\n'
             '  r = run_cmd(\n'
             '      ["mvt-android", "check-backup", "--output", str(mvt_out), "/case/evidence"],\n'
             '      stdout_path, stderr_path,\n'
             '  )\n'
             '  result = {\n'
             '      "status": "success" if r == 0 else "failed",\n'
             '      "exit_code": r,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": stderr_path.name,\n'
             '      "error": None if r == 0 else "mvt-android exited non-zero - see stderr '
             '(evidence must be a real Android .ab backup file)",\n'
             '  }',
  'is_entry_point': 1},
 {'module_id': 'network_conversations',
  'filename': 'main.yaml',
  'content': 'id: network_conversations\n'
             'argv:\n'
             '  - tshark\n'
             '  - -r\n'
             '  - /case/evidence\n'
             '  - -q\n'
             '  - -z\n'
             '  - conv,ip',
  'is_entry_point': 1},
 {'module_id': 'network_protocol_hierarchy',
  'filename': 'main.yaml',
  'content': 'id: network_protocol_hierarchy\n'
             'argv:\n'
             '  - tshark\n'
             '  - -r\n'
             '  - /case/evidence\n'
             '  - -q\n'
             '  - -z\n'
             '  - io,phs',
  'is_entry_point': 1},
 {'module_id': 'network_stream_extraction',
  'filename': 'main.yaml',
  'content': 'id: network_stream_extraction\n'
             'install:\n'
             '  apt: [tcpflow]\n'
             '  check: tcpflow\n'
             'script: |\n'
             '  from pathlib import Path\n'
             '\n'
             '  streams_dir = output_dir / "artifacts" / "streams"\n'
             '  streams_dir.mkdir(parents=True, exist_ok=True)\n'
             '\n'
             '  r = run_cmd(["tcpflow", "-o", str(streams_dir), "-r", "/case/evidence"], '
             'stdout_path, stderr_path)\n'
             '\n'
             '  stream_files = sorted(p for p in streams_dir.glob("*") if p.is_file() and p.suffix '
             '!= ".xml")\n'
             '  summary = [f"{p.name} ({p.stat().st_size} bytes)" for p in stream_files]\n'
             '  stdout_path.write_text(f"Streams extracted: {len(summary)}\\n" + '
             '"\\n".join(summary))\n'
             '\n'
             '  result = {\n'
             '      "status": "success" if r == 0 else "failed",\n'
             '      "exit_code": r,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": stderr_path.name,\n'
             '      "error": None if r == 0 else f"tcpflow exited {r}",\n'
             '  }',
  'is_entry_point': 1},
 {'module_id': 'static_capa_capabilities',
  'filename': 'main.yaml',
  'content': 'id: static_capa_capabilities\n'
             'argv:\n'
             '  - capa\n'
             '  - -r\n'
             '  - /opt/capa-rules\n'
             '  - /case/evidence',
  'is_entry_point': 1},
 {'module_id': 'static_floss_strings',
  'filename': 'main.yaml',
  'content': 'id: static_floss_strings\n'
             'script: |\n'
             '  min_length = int(options.get("min_length", 4))\n'
             '  r = run_cmd(\n'
             '      ["floss", "-n", str(min_length), "--only", "static", "--", "/case/evidence"],\n'
             '      stdout_path, stderr_path,\n'
             '  )\n'
             '  result = {\n'
             '      "status": "success" if r == 0 else "failed",\n'
             '      "exit_code": r,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": stderr_path.name,\n'
             '      "error": None if r == 0 else f"floss exited {r}",\n'
             '  }\n'
             'options:\n'
             '  min_length:\n'
             '    type: int\n'
             '    default: 4\n'
             '    min: 3\n'
             '    max: 64\n'
             '    label: Minimum string length',
  'is_entry_point': 1},
 {'module_id': 'windows_plaso_timeline',
  'filename': 'main.yaml',
  'content': 'id: windows_plaso_timeline\n'
             'script: |\n'
             '  from pathlib import Path\n'
             '\n'
             '  storage_file = output_dir / "timeline.plaso"\n'
             '  csv_file = output_dir / "timeline.csv"\n'
             '\n'
             '  rc1 = run_cmd(\n'
             '      ["log2timeline", "--status_view", "none", "--storage-file", str(storage_file), '
             '"/case/evidence"],\n'
             '      output_dir / "log2timeline.log", stderr_path,\n'
             '  )\n'
             '  rc2 = 1\n'
             '  if rc1 == 0:\n'
             '      rc2 = run_cmd(\n'
             '          ["psort", "-o", "dynamic", "-w", str(csv_file), str(storage_file)],\n'
             '          output_dir / "psort.log", stderr_path,\n'
             '      )\n'
             '\n'
             '  csv_text = csv_file.read_text() if csv_file.exists() else ""\n'
             '  stdout_path.write_text(csv_text or "(no timeline events extracted)")\n'
             '\n'
             '  result = {\n'
             '      "status": "success" if rc1 == 0 and rc2 == 0 else "failed",\n'
             '      "exit_code": rc2,\n'
             '      "stdout_file": stdout_path.name,\n'
             '      "stderr_file": stderr_path.name,\n'
             '      "error": None if rc1 == 0 and rc2 == 0 else "log2timeline/psort failed - see '
             'stderr",\n'
             '  }',
  'is_entry_point': 1}]

async def seed_categories() -> None:
    for row in CATEGORIES:
        await db.table("categories").upsert(
            row, update_columns=["name", "description", "sort_order"]
        )
    print(f"Seeded {len(CATEGORIES)} categories.")


async def seed_instances() -> None:
    for row in INSTANCES:
        await db.table("instances").upsert(
            {**row, "image_status": "unknown", "created_by": None},
            update_columns=[
                "display_name", "image_tag", "cpu_limit", "memory_limit",
                "pids_limit", "queue_name", "default_timeout_seconds", "is_active",
            ],
        )
    print(f"Seeded {len(INSTANCES)} instances.")


async def seed_plans() -> None:
    for row in PLANS:
        await db.table("plans").upsert(
            {
                **row,
                "resources": json.dumps(row["resources"]),
                "allowed_tiers": json.dumps(row["allowed_tiers"]),
            },
            update_columns=[
                "display_name", "description", "price_monthly", "price_annual",
                "resources", "allowed_tiers", "is_active", "sort_order",
            ],
        )
    print(f"Seeded {len(PLANS)} plans.")


async def seed_modules() -> None:
    for row in MODULES:
        await db.table("analysis_module_defs").upsert(
            {
                **row,
                "options_schema": json.dumps(row["options_schema"]) if row["options_schema"] else None,
                "pipeline_spec": json.dumps(row["pipeline_spec"]) if row["pipeline_spec"] else None,
                "created_by": None,
            },
            update_columns=[
                "display_name", "description", "supported_types", "parser_name",
                "category_id", "instance_id", "tier", "timeout_seconds",
                "options_schema", "pipeline_spec", "is_enabled", "status", "source",
            ],
        )
    print(f"Seeded {len(MODULES)} module definitions.")


async def seed_module_files() -> None:
    for row in MODULE_FILES:
        await db.table("module_files").upsert(
            {"id": new_id(), **row},
            update_columns=["content", "is_entry_point"],
        )
    print(f"Seeded {len(MODULE_FILES)} module files.")


async def seed_plan_instances() -> None:
    created = 0
    for row in PLAN_INSTANCES:
        exists = (
            await db.table("plan_instances")
            .where("plan_id", row["plan_id"])
            .where("instance_id", row["instance_id"])
            .exists()
        )
        if not exists:
            await db.table("plan_instances").create(row)
            created += 1
    print(f"Seeded plan-instance grants ({created} new, {len(PLAN_INSTANCES) - created} already present).")


async def main() -> None:
    await init_pool(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        db=Config.DB_NAME,
    )
    try:
        # Order matters: categories/instances/plans first (no deps), then
        # modules (depends on categories+instances), then module_files
        # (depends on modules), then plan_instances (depends on plans+instances).
        await seed_categories()
        await seed_instances()
        await seed_plans()
        await seed_modules()
        await seed_module_files()
        await seed_plan_instances()
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
