# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Content-addressed storage for base64 blobs.

Instead of embedding (often duplicated) base64 strings directly in result JSON,
we hash each blob and store it once under ``<output_dir>/base64/<hash>``. The
JSON field then holds the absolute path to that file. Reads are backward
compatible: a field may contain either an absolute path (new) or the raw
base64 string (old).
"""
import time
import threading
import hashlib
import os
from pathlib import Path

def _hash(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def write_base64(content, output_dir) -> str:
    """Store ``content`` under ``<output_dir>/base64/<hash>`` and return the
    absolute path to it. Trusts SHA-256 for dedup: if the path is already on
    disk, no write happens. ``None``/empty is returned unchanged.
    """
    if not content:
        return content
    if os.path.isfile(content):
        return content
    base64_dir = Path(output_dir) / 'base64'
    path = str((base64_dir / _hash(content)).resolve())
    if not os.path.exists(path):
        os.makedirs(base64_dir, exist_ok=True)
        tmp = f'{path}.tmp'
        with open(tmp, 'w', encoding='utf-8', errors='surrogateescape') as f:
            f.write(content)
        os.replace(tmp, path)
    return path

def read_base64(field_value) -> str:
    """Resolve a ``*_base64`` field to its actual base64 string.

    If ``field_value`` is a path to an existing file, return the file's
    content; otherwise assume it already is the base64 string and return it
    unchanged (backward compatible). ``None``/empty is returned unchanged.
    """
    if not field_value:
        return field_value
    if os.path.isfile(field_value):
        with open(field_value, 'r', encoding='utf-8', errors='surrogateescape') as f:
            return f.read()
    return field_value

def read_base64_sync(field_value) -> str:
    """Synchronous counterpart of :func:`read_base64` for non-async callers
    (e.g. Streamlit/Gradio UI)."""
    if not field_value:
        return field_value
    if os.path.isfile(field_value):
        with open(field_value, 'r', encoding='utf-8', errors='surrogateescape') as f:
            return f.read()
    return field_value

def offload_base64_fields(obj, output_dir):
    """Return a copy of ``obj`` with every base64 image field value replaced by
    its on-disk path, recursing through nested dicts/lists (so nested
    ``unpreferred_candidates`` are handled too). A field is treated as base64
    when its key contains ``"base64"``. Non-base64 scalars are shared, not
    copied, so the large base64 strings are the only thing replaced and the
    original object is never mutated.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and 'base64' in k and isinstance(v, str) and v:
                out[k] = write_base64(v, output_dir)
            else:
                out[k] = offload_base64_fields(v, output_dir)
        return out
    if isinstance(obj, list):
        return [offload_base64_fields(x, output_dir) for x in obj]
    return obj
