"""Bundled copy of the shared cleanup request contract for deployment packaging."""
from datetime import datetime, timedelta, timezone
import re

MAX_LAB_SECONDS = 7200
_RUN_ID = re.compile(r"^[0-9]{8,13}$")
_REVISION = re.compile(r"^[a-f0-9]{40}$")


def validate_cleanup_request(request: object) -> dict:
    if not isinstance(request, dict):
        raise ValueError("cleanup request must be an object")
    required = {"run_id", "source_revision", "cluster_name", "state_prefix", "started_at", "expires_at"}
    if set(request) != required:
        raise ValueError("cleanup request must contain only the exact required run identity fields")
    run_id = request["run_id"]
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("invalid run id")
    if request["cluster_name"] != f"fleet-lab-r{run_id}" or request["state_prefix"] != f"gcp-lab/runs/{run_id}":
        raise ValueError("cleanup target must be exactly this run")
    revision = request["source_revision"]
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision) or set(revision) == {"0"}:
        raise ValueError("invalid source revision")
    parsed = []
    for key in ("started_at", "expires_at"):
        value = request[key]
        if not isinstance(value, str):
            raise ValueError(f"{key} must be UTC ISO-8601")
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{key} must be UTC ISO-8601") from exc
        if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
            raise ValueError(f"{key} must be UTC ISO-8601")
        parsed.append(dt.astimezone(timezone.utc))
    if parsed[1] - parsed[0] != timedelta(seconds=MAX_LAB_SECONDS):
        raise ValueError("expiry must be exactly two hours after start")
    return request
