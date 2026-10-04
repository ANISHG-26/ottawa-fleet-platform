"""Upload bounded command failures to an exact private CI run prefix."""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

MAX_DIAGNOSTIC_BYTES = 256 * 1024


def upload_failure_diagnostic(*, prefix: str, stage: str, returncode: int,
                              stdout: str | bytes | None, stderr: str | bytes | None,
                              runner=subprocess.run) -> bool:
    """Store raw bounded output privately; reveal no URI or command in caller logs."""
    if not re.fullmatch(r"gs://[a-z0-9._-]+/gcp-lab/runs/[0-9]{8,13}/diagnostics", prefix):
        return False
    safe_stage = re.sub(r"[^a-zA-Z0-9_-]", "_", stage)[:40] or "command"

    def text(value: str | bytes | None) -> bytes:
        if value is None:
            return b""
        return value if isinstance(value, bytes) else value.encode("utf-8", errors="replace")

    # Preserve each stream's tail, where Terraform normally reports the cause.
    per_stream = 120 * 1024
    stderr_bytes, stdout_bytes = text(stderr), text(stdout)
    payload = (f"stage={safe_stage}\nexit_code={int(returncode)}\n--- stderr (tail) ---\n".encode() +
               stderr_bytes[-per_stream:] + b"\n--- stdout (tail) ---\n" + stdout_bytes[-per_stream:])
    payload = payload[-MAX_DIAGNOSTIC_BYTES:]
    uri = f"{prefix}/{uuid.uuid4().hex}.log"
    path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(prefix="ci-diagnostic-", suffix=".log", delete=False) as f:
            path = Path(f.name)
            if os.name != "nt":
                os.chmod(path, 0o600)
            f.write(payload)
        result = runner(["gcloud", "storage", "cp", "--if-generation-match=0", str(path), uri],
                        text=True, capture_output=True, check=False)
        return result.returncode == 0
    except Exception:
        return False
    finally:
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
