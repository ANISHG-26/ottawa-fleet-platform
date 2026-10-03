"""Validate a durable cleanup request for one time-limited GCP lab run."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import os
import re
import secrets
import subprocess
import tarfile
from pathlib import Path

MAX_LAB_SECONDS = 2 * 60 * 60
_REVISION = re.compile(r"^[a-f0-9]{40}$")
# `fleet-lab-r` uses 11 characters; Terraform/GKE names cap at 24.
_RUN_ID = re.compile(r"^[0-9]{8,13}$")
_PROJECT_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$")

_REVIEWED_TFVARS = {
    "project_id", "zone", "node_service_account_id", "machine_type", "node_count",
    "node_disk_size_gb", "resource_plan_reviewed", "review_project_id", "review_zone",
    "inventory_reference", "quota_reviewed", "pricing_reviewed", "workload_sizing_reference",
    "workload_sizing_reviewed", "teardown_owner_reference", "inventory_matches_review",
    "reviewed_resource_ceiling", "ceiling_matches_review", "project_zone_match_reviewed",
}


def _utc_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be a UTC ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field} must be a UTC ISO-8601 timestamp")
    return parsed.astimezone(timezone.utc)


def validate_cleanup_request(request: object) -> dict:
    """Reject broad or stale cleanup selectors before any cloud API is called."""
    if not isinstance(request, dict):
        raise ValueError("cleanup request must be an object")
    required = {"run_id", "source_revision", "cluster_name", "state_prefix", "started_at", "expires_at"}
    if set(request) != required:
        raise ValueError("cleanup request must contain only the exact required run identity fields")

    run_id = request["run_id"]
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("run_id must be a numeric immutable CI run ID")
    if request["cluster_name"] != f"fleet-lab-r{run_id}":
        raise ValueError("cluster_name must identify exactly this CI run")
    if request["state_prefix"] != f"gcp-lab/runs/{run_id}":
        raise ValueError("state_prefix must be unique to this CI run")
    revision = request["source_revision"]
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision) or set(revision) == {"0"}:
        raise ValueError("source_revision must be a non-placeholder full Git commit SHA")

    started = _utc_timestamp(request["started_at"], "started_at")
    expires = _utc_timestamp(request["expires_at"], "expires_at")
    if expires - started != timedelta(seconds=MAX_LAB_SECONDS):
        raise ValueError("expires_at must be exactly two hours after started_at")
    return request


def write_run_inputs(*, run_id: str, source_revision: str, started_at: str, expires_at: str,
                     state_bucket: str, tfvars_json: str, output_dir: str | Path) -> dict:
    """Build private, run-scoped backend/tfvars files from reviewed gate inputs."""
    state_prefix = f"gcp-lab/runs/{run_id}"
    cluster_name = f"fleet-lab-r{run_id}"
    request = {
        "run_id": run_id,
        "source_revision": source_revision,
        "cluster_name": cluster_name,
        "state_prefix": state_prefix,
        "started_at": started_at,
        "expires_at": expires_at,
    }
    validate_cleanup_request(request)
    if not isinstance(state_bucket, str) or not _BUCKET.fullmatch(state_bucket):
        raise ValueError("state_bucket must be a valid private GCS bucket name")
    try:
        reviewed = json.loads(tfvars_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("private Terraform variables must be a JSON object") from exc
    if not isinstance(reviewed, dict):
        raise ValueError("private Terraform variables must be a JSON object")
    allowed_extra = {
        "cluster_name", "teardown_deadline", "retained_network_name", "cloudsql_enabled",
        "cloudsql_plan_reviewed", "cloudsql_quota_reviewed", "cloudsql_pricing_reviewed",
        "cloudsql_inventory_reference", "database_password",
    }
    unknown = set(reviewed) - (_REVIEWED_TFVARS | allowed_extra)
    if unknown:
        raise ValueError("unexpected private Terraform variables: " + ", ".join(sorted(unknown)))
    missing = _REVIEWED_TFVARS - reviewed.keys()
    if missing:
        raise ValueError("missing reviewed Terraform variables: " + ", ".join(sorted(missing)))
    if not _PROJECT_ID.fullmatch(str(reviewed["project_id"])) or reviewed["review_project_id"] != reviewed["project_id"]:
        raise ValueError("private Terraform project must match its reviewed inventory")
    if not isinstance(reviewed["zone"], str) or reviewed["review_zone"] != reviewed["zone"]:
        raise ValueError("private Terraform zone must match its reviewed inventory")
    expected = {
        "machine_type": "e2-standard-2", "node_count": 1, "node_disk_size_gb": 30,
        "resource_plan_reviewed": True, "quota_reviewed": True, "pricing_reviewed": True,
        "workload_sizing_reviewed": True, "inventory_matches_review": True,
        "reviewed_resource_ceiling": 1, "ceiling_matches_review": True,
        "project_zone_match_reviewed": True,
    }
    for key, value in expected.items():
        if type(reviewed[key]) is not type(value) or reviewed[key] != value:
            raise ValueError(f"{key} must match the reviewed first-lab shape and gates")
    for key in ("inventory_reference", "workload_sizing_reference", "teardown_owner_reference", "node_service_account_id"):
        if not isinstance(reviewed[key], str) or len(reviewed[key].strip()) < 3:
            raise ValueError(f"{key} must identify an explicit private reviewed input")

    values = dict(reviewed)
    values["cluster_name"] = cluster_name
    if not isinstance(values.get("retained_network_name"), str) or not values["retained_network_name"].strip():
        raise ValueError("retained_network_name must identify the separately reviewed CI network")
    if values.get("cloudsql_enabled") is not True:
        raise ValueError("CI lab runs require the reviewed private Cloud SQL database")
    for key in ("cloudsql_plan_reviewed", "cloudsql_quota_reviewed", "cloudsql_pricing_reviewed"):
        if values.get(key) is not True:
            raise ValueError(f"{key} must be true for the reviewed CI database shape")
    if not isinstance(values.get("cloudsql_inventory_reference"), str) or len(values["cloudsql_inventory_reference"].strip()) < 3:
        raise ValueError("cloudsql_inventory_reference must identify the private reviewed database inputs")
    values["database_password"] = secrets.token_urlsafe(36)
    expiry = _utc_timestamp(expires_at, "expires_at")
    values["teardown_deadline"] = expiry.isoformat(timespec="seconds").replace("+00:00", "Z")
    root = Path(output_dir).expanduser().resolve(strict=False)
    repo_root = Path(__file__).resolve().parents[1]
    if root.is_relative_to(repo_root):
        raise ValueError("private run inputs must be written outside the public repository")
    root.mkdir(parents=True, exist_ok=True)
    tfvars_path = root / "terraform.tfvars.json"
    backend_path = root / "backend.hcl"
    request_path = root / "cleanup-request.json"
    tfvars_path.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    backend_path.write_text(
        f'bucket = "{state_bucket}"\nprefix = "{state_prefix}"\n', encoding="utf-8"
    )
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    if os.name != "nt":
        for path in (tfvars_path, backend_path, request_path):
            path.chmod(0o600)
    return {
        "tfvars": str(tfvars_path),
        "backend": str(backend_path),
        "request_file": str(request_path),
        "request": request,
    }


def create_source_archive(*, source_revision: str, output_path: str | Path,
                          repo_root: str | Path | None = None,
                          paths: tuple[str, ...] = ("terraform/lab", "scripts/lab_cleanup.py",
                                                    "scripts/cleanup_execute.py", "scripts/__init__.py")) -> Path:
    """Archive only cleanup code and Terraform from the exact committed revision."""
    if not isinstance(source_revision, str) or not _REVISION.fullmatch(source_revision) or set(source_revision) == {"0"}:
        raise ValueError("source_revision must be a non-placeholder full Git commit SHA")
    root = Path(repo_root or Path(__file__).resolve().parents[1]).resolve(strict=True)
    output = Path(output_path).expanduser().resolve(strict=False)
    if output.is_relative_to(root):
        raise ValueError("private source archive must be written outside the public repository")
    output.parent.mkdir(parents=True, exist_ok=True)
    allowed = {"terraform/lab", "scripts/lab_cleanup.py", "scripts/cleanup_execute.py", "scripts/__init__.py"}
    if not paths or set(paths) - allowed:
        raise ValueError("source archive paths must use the cleanup source allowlist")
    archive = subprocess.run(
        ["git", "archive", "--format=tar.gz", source_revision, "--", *paths], cwd=root,
        check=True, capture_output=True,
    ).stdout
    # Reject malformed archives before they are uploaded to durable cleanup storage.
    import io
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as source:
        if not source.getmembers():
            raise ValueError("source archive is empty")
        for member in source.getmembers():
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise ValueError("source archive contains an unsafe path")
    output.write_bytes(archive)
    if os.name != "nt":
        output.chmod(0o600)
    return output
