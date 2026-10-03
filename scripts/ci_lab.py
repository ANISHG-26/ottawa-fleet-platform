"""Provision one reviewed CI lab run after registering its durable expiry task."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from scripts.lab_cleanup import MAX_LAB_SECONDS, create_source_archive, write_run_inputs

ROOT = Path(__file__).resolve().parents[1]
_SHA = re.compile(r"^[a-f0-9]{40}$")
_RUN_ID = re.compile(r"^[0-9]{8,13}$")


def validate_dispatch(event_name: str, ref: str, revision: str, checkout_revision: str) -> None:
    """Require a manually dispatched run from the protected production branch."""
    if event_name != "workflow_dispatch":
        raise ValueError("lab provisioning accepts workflow_dispatch only")
    if ref != "refs/heads/main":
        raise ValueError("lab provisioning accepts the trusted refs/heads/main ref only")
    if not isinstance(revision, str) or not _SHA.fullmatch(revision) or revision != checkout_revision:
        raise ValueError("workflow revision must be the exact full SHA checked out")


def validate_run_id(run_id: str) -> str:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        raise ValueError("GitHub Actions run ID must be an 8-to-13 digit immutable ID")
    return run_id


def expiry_from_run_start(started_at: str) -> tuple[str, str]:
    """Derive the fixed deadline from GitHub's run_started_at value."""
    if not isinstance(started_at, str):
        raise ValueError("Actions run_started_at is required")
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Actions run_started_at must be an ISO-8601 timestamp") from exc
    if started.tzinfo is None or started.utcoffset() != timedelta(0):
        raise ValueError("Actions run_started_at must be a UTC timestamp")
    started = started.astimezone(timezone.utc)
    expires = started + timedelta(seconds=MAX_LAB_SECONDS)
    return (
        started.isoformat(timespec="seconds").replace("+00:00", "Z"),
        expires.isoformat(timespec="seconds").replace("+00:00", "Z"),
    )


def fetch_run_started_at(api_url: str, repository: str, run_id: str) -> str:
    """Read run start from the Actions API without placing a token in this job."""
    validate_run_id(run_id)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must be owner/name")
    url = f"{api_url.rstrip('/')}/repos/{repository}/actions/runs/{run_id}"
    request = Request(url, headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    try:
        with urlopen(request, timeout=20) as response:
            body = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError("could not read the Actions run start timestamp") from exc
    if not isinstance(body, dict) or not body.get("run_started_at"):
        raise ValueError("Actions API response did not contain run_started_at")
    return body["run_started_at"]


def _run(command: list[str], *, cwd: Path, runner=subprocess.run) -> None:
    """Run quietly so secrets, Terraform values and provider output stay out of logs."""
    result = runner(command, cwd=cwd, text=True, capture_output=True, check=False)
    if result.returncode:
        raise RuntimeError(f"provisioning command failed ({Path(command[0]).name}, exit {result.returncode})")


def _access_token(runner=subprocess.run) -> str:
    result = runner(["gcloud", "auth", "print-access-token"], cwd=ROOT,
                    text=True, capture_output=True, check=False)
    if result.returncode or not result.stdout.strip():
        raise RuntimeError("could not obtain a short-lived Google access token")
    return result.stdout.strip()


def _gcs_url(bucket: str, name: str, *, upload: bool = False, generation: str | None = None) -> str:
    escaped = quote(name, safe="")
    if upload:
        return (f"https://storage.googleapis.com/upload/storage/v1/b/{bucket}/o"
                f"?uploadType=media&name={escaped}&ifGenerationMatch=0")
    suffix = f"?ifGenerationMatch={quote(generation, safe='')}" if generation else ""
    return f"https://storage.googleapis.com/storage/v1/b/{bucket}/o/{escaped}{suffix}"


def _gcs_call(method: str, url: str, token: str, *, body: bytes | None = None,
              opener=urlopen) -> tuple[dict, object]:
    request = Request(url, data=body, method=method,
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"})
    with opener(request, timeout=30) as response:
        raw = response.read()
        return (json.loads(raw) if raw else {}, response)


def acquire_active_lease(*, bucket: str, request: dict, token: str, opener=urlopen) -> tuple[str, bool]:
    """Acquire the single-live-run guard, accepting only an identical same-run resume."""
    identity = json.dumps(request, sort_keys=True, separators=(",", ":")).encode()
    name = "gcp-lab/ci-active-run.json"
    try:
        metadata, _ = _gcs_call("POST", _gcs_url(bucket, name, upload=True), token,
                                body=identity, opener=opener)
        generation = metadata.get("generation")
        if not generation:
            raise RuntimeError("active lab lease upload did not return an object generation")
        return str(generation), False
    except HTTPError as exc:
        if exc.code != 412:
            raise RuntimeError("could not acquire the active lab lease") from exc
    try:
        metadata, _ = _gcs_call("GET", _gcs_url(bucket, name), token, opener=opener)
        generation = str(metadata.get("generation", ""))
    except Exception as exc:
        raise RuntimeError("an active CI lab lease already exists") from exc
    # alt=media is raw JSON, so use a second raw read rather than interpreting it as an API object.
    raw_request = Request(_gcs_url(bucket, name) + "?alt=media",
                          headers={"Authorization": f"Bearer {token}"})
    try:
        with opener(raw_request, timeout=30) as response:
            existing_request = json.loads(response.read())
    except Exception as exc:
        raise RuntimeError("an active CI lab lease exists but its identity cannot be verified") from exc
    if existing_request != request or not generation:
        raise RuntimeError("another CI lab run still owns the active lease")
    return generation, True


def release_active_lease(*, bucket: str, generation: str, token: str, opener=urlopen) -> None:
    """Compare-and-delete only the exact lease generation this runner acquired."""
    request = Request(_gcs_url(bucket, "gcp-lab/ci-active-run.json", generation=generation),
                      headers={"Authorization": f"Bearer {token}"}, method="DELETE")
    try:
        with opener(request, timeout=30):
            pass
    except Exception as exc:
        raise RuntimeError("could not release the exact active lab lease generation") from exc


def _create_task(*, project: str, location: str, queue: str, task_id: str,
                 url: str, audience: str, invoker: str, schedule_time: str,
                 run_id: str, token: str, opener=urlopen) -> None:
    parent = f"projects/{project}/locations/{location}/queues/{queue}"
    task = {
        "name": f"{parent}/tasks/{task_id}",
        "scheduleTime": schedule_time,
        "httpRequest": {
            "httpMethod": "POST", "url": url,
            "headers": {"Content-Type": "application/json"},
            "body": base64.b64encode(json.dumps({"run_id": run_id}, separators=(",", ":")).encode()).decode("ascii"),
            "oidcToken": {"serviceAccountEmail": invoker, "audience": audience},
        },
    }
    request = Request(
        f"https://cloudtasks.googleapis.com/v2/{parent}/tasks",
        data=json.dumps({"task": task, "responseView": "FULL"}, separators=(",", ":")).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with opener(request, timeout=30) as response:
            result = json.loads(response.read() or b"{}")
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        if not isinstance(exc, HTTPError) or exc.code != 409:
            raise RuntimeError("durable expiry task registration failed") from exc
        existing_request = Request(f"https://cloudtasks.googleapis.com/v2/{task['name']}?responseView=FULL",
                                   headers={"Authorization": f"Bearer {token}"})
        try:
            with opener(existing_request, timeout=30) as response:
                result = json.loads(response.read())
        except Exception as verify_error:
            raise RuntimeError("existing expiry task could not be verified for same-run resume") from verify_error
    if not isinstance(result, dict) or result.get("name") != task["name"]:
        raise RuntimeError("Cloud Tasks did not confirm the exact expiry task")
    registered = result.get("httpRequest", {})
    expected = task["httpRequest"]
    if (result.get("scheduleTime") != task["scheduleTime"] or
        registered.get("url") != expected["url"] or
        registered.get("httpMethod") != expected["httpMethod"] or
        registered.get("body") != expected["body"] or
        registered.get("oidcToken") != expected["oidcToken"]):
        raise RuntimeError("existing expiry task does not match this exact run's cleanup contract")


def _upload(path: Path, uri: str, runner=subprocess.run) -> None:
    result = runner(["gcloud", "storage", "cp", "--if-generation-match=0", str(path), uri],
                    cwd=ROOT, text=True, capture_output=True, check=False)
    if result.returncode:
        with tempfile.NamedTemporaryFile(prefix="fleet-lab-existing-", delete=False) as target:
            existing = Path(target.name)
        try:
            fetched = runner(["gcloud", "storage", "cp", uri, str(existing)], cwd=ROOT,
                            text=True, capture_output=True, check=False)
            if fetched.returncode or existing.read_bytes() != path.read_bytes():
                raise RuntimeError("immutable private run input already exists with different contents")
        finally:
            existing.unlink(missing_ok=True)


def _reuse_private_tfvars(path: Path, uri: str, runner=subprocess.run) -> None:
    """Reuse this run's original randomized DB password on a same-run retry."""
    with tempfile.NamedTemporaryFile(prefix="fleet-lab-tfvars-", delete=False) as target:
        existing = Path(target.name)
    try:
        result = runner(["gcloud", "storage", "cp", uri, str(existing)], cwd=ROOT,
                        text=True, capture_output=True, check=False)
        if result.returncode:
            raise RuntimeError("same-run lease exists but its immutable Terraform inputs are unavailable")
        stored = json.loads(existing.read_text(encoding="utf-8"))
        current = json.loads(path.read_text(encoding="utf-8"))
        stored_password = stored.get("database_password")
        stored["database_password"] = current.get("database_password")
        if stored != current or not isinstance(stored_password, str) or len(stored_password) < 32:
            raise RuntimeError("same-run lease inputs do not match this exact reviewed revision")
        current["database_password"] = stored_password
        path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        if os.name != "nt":
            path.chmod(0o600)
    finally:
        existing.unlink(missing_ok=True)


def run_pipeline(environment: dict[str, str] | None = None, *, runner=subprocess.run,
                 opener=urlopen, source_root: Path = ROOT) -> dict:
    """Upload immutable private inputs, schedule cleanup, then apply and bootstrap."""
    env = dict(os.environ if environment is None else environment)
    event_name = env["GITHUB_EVENT_NAME"]
    ref = env["GITHUB_REF"]
    revision = env["GITHUB_SHA"]
    checked_out = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source_root,
                                 text=True, capture_output=True, check=True).stdout.strip()
    validate_dispatch(event_name, ref, revision, checked_out)
    run_id = validate_run_id(env["GITHUB_RUN_ID"])
    project = env["GCP_PROJECT_ID"]
    bucket = env["LAB_STATE_BUCKET"]
    for name in ("LAB_TFVARS_JSON", "GCP_PROJECT_ID", "LAB_STATE_BUCKET", "LAB_TASK_LOCATION",
                 "LAB_TASK_QUEUE", "LAB_SHUTDOWN_URL", "LAB_TASK_INVOKER_SERVICE_ACCOUNT",
                 "GITHUB_API_URL", "GITHUB_REPOSITORY"):
        if not env.get(name, "").strip():
            raise ValueError(f"required private environment value is missing: {name}")
    try:
        reviewed_values = json.loads(env["LAB_TFVARS_JSON"])
    except json.JSONDecodeError as exc:
        raise ValueError("private Terraform variables must be a JSON object") from exc
    if not isinstance(reviewed_values, dict) or reviewed_values.get("project_id") != project or reviewed_values.get("review_project_id") != project:
        raise ValueError("configured GCP project must match the private reviewed Terraform project")

    started_at, expires_at = expiry_from_run_start(
        fetch_run_started_at(env["GITHUB_API_URL"], env["GITHUB_REPOSITORY"], run_id)
    )
    run_prefix = f"gcp-lab/runs/{run_id}"
    base_uri = f"gs://{bucket}/{run_prefix}"
    work = Path(tempfile.mkdtemp(prefix="fleet-lab-"))
    apply_started = False
    task_registered = False
    lease_generation: str | None = None
    lease_resumed = False
    token: str | None = None
    try:
        outputs = write_run_inputs(
            run_id=run_id, source_revision=revision, started_at=started_at,
            expires_at=expires_at, state_bucket=bucket,
            tfvars_json=env["LAB_TFVARS_JSON"], output_dir=work / "private",
        )
        archive = create_source_archive(source_revision=revision, output_path=work / "source.tgz",
                                        repo_root=source_root,
                                        paths=("terraform/lab", "scripts/lab_cleanup.py",
                                               "scripts/cleanup_execute.py", "scripts/__init__.py"))
        inputs = [
            (Path(outputs["request_file"]), f"{base_uri}/request.json"),
            (archive, f"{base_uri}/source.tgz"),
            (Path(outputs["tfvars"]), f"{base_uri}/terraform.tfvars.json"),
            (Path(outputs["backend"]), f"{base_uri}/backend.hcl"),
        ]
        token = _access_token(runner)
        lease_generation, resumed = acquire_active_lease(
            bucket=bucket, request=outputs["request"], token=token, opener=opener,
        )
        lease_resumed = resumed
        if resumed:
            _reuse_private_tfvars(Path(outputs["tfvars"]), f"{base_uri}/terraform.tfvars.json", runner)
        for path, uri in inputs:
            _upload(path, uri, runner)

        _create_task(
            project=project, location=env["LAB_TASK_LOCATION"], queue=env["LAB_TASK_QUEUE"],
            task_id=f"fleet-r{run_id}", url=env["LAB_SHUTDOWN_URL"],
            audience=env["LAB_SHUTDOWN_URL"], invoker=env["LAB_TASK_INVOKER_SERVICE_ACCOUNT"],
            schedule_time=expires_at, run_id=run_id, token=token, opener=opener,
        )
        task_registered = True

        terraform = source_root / "terraform" / "lab"
        _run(["terraform", "init", "-input=false", f"-backend-config={outputs['backend']}"], cwd=terraform, runner=runner)
        plan = work / "reviewed.tfplan"
        _run(["terraform", "plan", "-input=false", f"-var-file={outputs['tfvars']}", f"-out={plan}"], cwd=terraform, runner=runner)
        if datetime.now(timezone.utc) >= datetime.fromisoformat(expires_at.replace("Z", "+00:00")):
            raise RuntimeError("the fixed two-hour expiry elapsed before Terraform apply")
        apply_started = True
        _run(["terraform", "apply", "-input=false", str(plan)], cwd=terraform, runner=runner)

        if datetime.now(timezone.utc) >= datetime.fromisoformat(expires_at.replace("Z", "+00:00")):
            raise RuntimeError("the fixed two-hour expiry elapsed before cluster bootstrap")
        kubeconfig = work / "kubeconfig"
        _run(["python", "-m", "scripts.gcp_lab", "bootstrap", "--project", project,
              "--zone", json.loads(env["LAB_TFVARS_JSON"])["zone"],
              "--cluster", f"fleet-lab-r{run_id}", "--kubeconfig", str(kubeconfig)],
             cwd=source_root, runner=runner)
        return {"run_id": run_id, "expires_at": expires_at, "task": f"fleet-r{run_id}"}
    except Exception:
        if task_registered:
            # Invoke the exact already-registered cleanup task now as a failure backstop.
            try:
                _run(["gcloud", "tasks", "run", f"fleet-r{run_id}",
                      f"--queue={env['LAB_TASK_QUEUE']}", f"--location={env['LAB_TASK_LOCATION']}",
                      f"--project={project}"], cwd=ROOT, runner=runner)
            except Exception:
                pass
        elif lease_generation and token and not lease_resumed:
            try:
                release_active_lease(bucket=bucket, generation=lease_generation,
                                     token=token, opener=opener)
            except Exception:
                pass
        raise
    finally:
        # Keep all values and plans outside the checkout; remove the private runner copy.
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def main() -> int:
    try:
        result = run_pipeline()
        print(f"Provisioned bounded CI lab run {result['run_id']}; scheduled expiry {result['expires_at']}.")
        return 0
    except Exception as exc:
        print(f"CI lab provisioning stopped: {exc}", file=__import__("sys").stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
