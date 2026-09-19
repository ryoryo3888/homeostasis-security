"""Record file/runtime identity for resume comparisons, not scientific approval.

Hashes describe the files on disk when collected. They are not independent
proof of which code executed, model determinism, or a tamper-proof signature.
"""
from __future__ import annotations

import hashlib
from importlib.metadata import version
from pathlib import Path
import platform


def runtime_identity() -> dict:
    return {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "packages": {name: version(name) for name in
                     ("google-genai", "pydantic", "httpx", "httpcore")},
    }


def execution_identity(source_root: Path, inputs: dict[str, Path], settings: dict) -> dict:
    sources = [source_root / name for name in
               ("final_experiment_runner.py", "model_response_json.py",
                "response_receipts.py", "provider_retry.py", "provider_response.py")]
    sources.extend(sorted((source_root / "homeostasis_core").rglob("*.py")))
    return {
        "format": "homeostasis_resume_identity_v1",
        "source_sha256": {str(path.relative_to(source_root)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sources},
        "input_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest()
                         for name, path in sorted(inputs.items())},
        "runtime": runtime_identity(),
        "settings": settings,
    }
