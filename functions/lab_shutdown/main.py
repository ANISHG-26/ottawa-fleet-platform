"""Authenticated, run-scoped Cloud Run cleanup dispatcher."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import json
import os
import re
from typing import Any
from urllib.parse import quote

from scripts_validator import validate_cleanup_request


_RUN_ID = re.compile(r"^[0-9]{8,13}$")
_TERMINAL = {"SUCCESS", "FAILURE", "CANCELLED", "TIMEOUT", "EXPIRED"}
_MAX_ATTEMPTS = 3
_POLL_SECONDS = 90
_LAUNCH_LEASE_SECONDS = 600


class GoogleBackend:
    """Small REST adapter; all resource selectors come from private env/config."""

    def __init__(self, env: dict[str, str], session: Any | None = None):
        self.env = env
        if session is None:
            from google.auth import default
            from google.auth.transport.requests import AuthorizedSession
            credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            session = AuthorizedSession(credentials)
        self.http = session
        self.project = env["PROJECT_ID"]
        self.project_number = env.get("PROJECT_NUMBER")
        self.project_aliases = {self.project}
        if self.project_number:
            self.project_aliases.add(self.project_number)
        self.bucket = env["STATE_BUCKET"]
        self.retained_network_name = env["EXPECTED_RETAINED_NETWORK"]
        self.location = env["CLOUD_BUILD_LOCATION"]
        self.queue = env["TASK_QUEUE"]
        self.function_url = env["FUNCTION_URL"].rstrip("/")
        self.cleanup_sa = env["CLEANUP_SERVICE_ACCOUNT"]

    def _get(self, url: str, **kwargs: Any) -> dict:
        response = self.http.get(url, timeout=30, **kwargs)
        if response.status_code == 404:
            return {}
        response.raise_for_status()
        return response.json()

    def _post(self, url: str, body: dict, **kwargs: Any) -> dict:
        response = self.http.post(url, json=body, timeout=30, **kwargs)
        if response.status_code not in (200, 201):
            response.raise_for_status()
        return response.json() if response.content else {}

    def read_object(self, name: str) -> tuple[bytes, str] | None:
        base = f"https://storage.googleapis.com/storage/v1/b/{quote(self.bucket, safe='')}/o/{quote(name, safe='')}"
        meta = self._get(base, params={"fields": "generation"})
        if not meta:
            return None
        response = self.http.get(base, params={"alt": "media", "generation": meta["generation"]}, timeout=30)
        response.raise_for_status()
        return response.content, str(meta["generation"])

    def write_object_cas(self, name: str, value: dict, generation: str | None) -> str | None:
        url = f"https://storage.googleapis.com/upload/storage/v1/b/{self.bucket}/o"
        params = {"uploadType": "media", "name": name,
                  "ifGenerationMatch": generation if generation is not None else "0"}
        response = self.http.post(url, params=params, data=json.dumps(value).encode(),
                                  headers={"Content-Type": "application/json"}, timeout=30)
        if response.status_code == 412:
            return None
        response.raise_for_status()
        return str(response.json()["generation"])

    def list_builds(self, tag: str) -> list[dict]:
        url = f"https://cloudbuild.googleapis.com/v1/projects/{self.project}/locations/{self.location}/builds"
        result = self._get(url, params={"filter": f"tags='{tag}'", "pageSize": 100})
        return result.get("builds", [])

    def get_build(self, name: str) -> dict:
        return self._get(f"https://cloudbuild.googleapis.com/v1/{name}")

    def create_build(self, tag: str, run_id: str, source_generation: str,
                     request_uri: str, tfvars_uri: str, backend_uri: str) -> dict:
        parent = f"projects/{self.project}/locations/{self.location}"
        config = {
            "source": {"storageSource": {"bucket": self.bucket,
                "object": f"gcp-lab/runs/{run_id}/source.tgz", "generation": source_generation}},
            "tags": [tag], "serviceAccount": f"projects/{self.project}/serviceAccounts/{self.cleanup_sa}",
            "timeout": "3600s",
            "options": {"logging": "CLOUD_LOGGING_ONLY"},
            "steps": [{"name": "gcr.io/google.com/cloudsdktool/google-cloud-cli:stable@sha256:73a97b855d386c74bee3facd59ccc261006c55a9812b7913fa6b93816010a1bc",
                "entrypoint": "python3", "args": ["-m", "scripts.cleanup_execute",
                    "--request-uri", request_uri, "--tfvars-uri", tfvars_uri,
                    "--backend-uri", backend_uri],
                "env": [f"EXPECTED_PROJECT={self.project}", f"EXPECTED_BUCKET={self.bucket}",
                        f"EXPECTED_RETAINED_NETWORK={self.retained_network_name}"]}],
        }
        operation = self._post(f"https://cloudbuild.googleapis.com/v1/{parent}/builds", config,
                               params={"projectId": self.project})
        if not isinstance(operation, dict) or operation.get("error"):
            raise RuntimeError("Cloud Build rejected the cleanup build request")
        metadata = operation.get("metadata")
        build = metadata.get("build") if isinstance(metadata, dict) else None
        if build is None and operation.get("done") is True:
            build = operation.get("response")
        if not isinstance(build, dict):
            raise RuntimeError("Cloud Build create operation did not include its build resource")
        name = build.get("name")
        build_id = build.get("id")
        project_id = build.get("projectId")
        if not isinstance(build_id, str) or not re.fullmatch(r"[A-Za-z0-9-]+", build_id):
            raise RuntimeError("Cloud Build response omitted a valid build ID")
        if not isinstance(project_id, str) or project_id not in self.project_aliases:
            raise RuntimeError("Cloud Build returned a build outside the configured project")
        path_match = (re.fullmatch(r"projects/([^/]+)/locations/([^/]+)/builds/([^/]+)", name)
                      if isinstance(name, str) else None)
        if (not path_match or path_match.group(1) not in self.project_aliases or
                path_match.group(2) != self.location or path_match.group(3) != build_id):
            raise RuntimeError("Cloud Build returned a build outside the configured project and location")
        if not isinstance(build.get("status"), str) or not build["status"]:
            raise RuntimeError("Cloud Build response omitted the build status")
        if tag not in build.get("tags", []):
            raise RuntimeError("Cloud Build response did not confirm the run cleanup tag")
        normalized = dict(build)
        normalized["name"] = f"projects/{self.project}/locations/{self.location}/builds/{build_id}"
        return normalized

    def create_poll_task(self, run_id: str, attempt: int, delay: int = _POLL_SECONDS) -> None:
        parent = f"projects/{self.project}/locations/{self.env['TASKS_LOCATION']}/queues/{self.queue}"
        task_id = f"poll-{run_id}-{attempt}-{int(datetime.now(timezone.utc).timestamp()) // delay}"
        body = {"task": {"name": f"{parent}/tasks/{task_id}",
            "scheduleTime": datetime.fromtimestamp(datetime.now(timezone.utc).timestamp()+delay, timezone.utc).isoformat(),
            "httpRequest": {"httpMethod": "POST", "url": self.function_url,
                "headers": {"Content-Type": "application/json"},
                "body": base64.b64encode(json.dumps({"run_id": run_id}).encode()).decode(),
                "oidcToken": {"serviceAccountEmail": self.env["TASK_INVOKER_SERVICE_ACCOUNT"],
                              "audience": self.function_url}}}}
        response = self.http.post(f"https://cloudtasks.googleapis.com/v2/{parent}/tasks", json=body, timeout=30)
        if response.status_code == 409:
            return
        response.raise_for_status()

    def release_active_lease(self, run_id: str) -> bool:
        name = "gcp-lab/ci-active-run.json"
        obj = self.read_object(name)
        if obj is None:
            return False
        try:
            lease = json.loads(obj[0])
        except (ValueError, TypeError):
            return False
        if lease.get("run_id") != run_id:
            return False
        response = self.http.delete(
            f"https://storage.googleapis.com/storage/v1/b/{quote(self.bucket, safe='')}/o/{quote(name, safe='')}",
            params={"ifGenerationMatch": obj[1]}, timeout=30)
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True


def _env() -> dict[str, str]:
    required = ("PROJECT_ID", "STATE_BUCKET", "EXPECTED_RETAINED_NETWORK", "TASK_QUEUE", "TASKS_LOCATION", "CLOUD_BUILD_LOCATION",
                "TASK_INVOKER_SERVICE_ACCOUNT", "CLEANUP_SERVICE_ACCOUNT", "FUNCTION_URL")
    env = {key: os.environ[key] for key in required}
    if os.environ.get("PROJECT_NUMBER"):
        if not re.fullmatch(r"[0-9]+", os.environ["PROJECT_NUMBER"]):
            raise ValueError("invalid configured project number")
        env["PROJECT_NUMBER"] = os.environ["PROJECT_NUMBER"]
    if not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", env["PROJECT_ID"]):
        raise ValueError("invalid configured project")
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]", env["STATE_BUCKET"]):
        raise ValueError("invalid configured bucket")
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,61}[a-z0-9]", env["EXPECTED_RETAINED_NETWORK"]):
        raise ValueError("invalid configured retained network")
    return env


def dispatch(run_id: object, backend: Any, now: datetime | None = None) -> tuple[dict, int]:
    if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id):
        return {"error": "invalid run_id"}, 400
    prefix = f"gcp-lab/runs/{run_id}"
    get_obj = backend.read_object
    req_obj, src_obj, vars_obj, backend_obj = (get_obj(f"{prefix}/{name}") for name in
                                                ("request.json", "source.tgz", "terraform.tfvars.json", "backend.hcl"))
    if not all((req_obj, src_obj, vars_obj, backend_obj)):
        return {"error": "run inputs are incomplete"}, 404
    try:
        request = validate_cleanup_request(json.loads(req_obj[0]))
    except (ValueError, TypeError, json.JSONDecodeError):
        return {"error": "invalid cleanup request"}, 400
    if request["run_id"] != run_id:
        return {"error": "run identity mismatch"}, 400
    # Validate private state selectors independently; request bodies never choose a URI/project.
    if request["state_prefix"] != prefix or request["cluster_name"] != f"fleet-lab-r{run_id}":
        return {"error": "unsafe cleanup selector"}, 400
    try:
        tfvars = json.loads(vars_obj[0])
    except (ValueError, TypeError):
        return {"error": "invalid private Terraform variables"}, 400
    if (not isinstance(tfvars, dict) or tfvars.get("project_id") != backend.project or
            tfvars.get("cluster_name") != request["cluster_name"] or
            tfvars.get("retained_network_name") != backend.retained_network_name):
        return {"error": "private Terraform variables do not match this configured run"}, 400
    expected_backend = f'bucket = "{backend.bucket}"\nprefix = "{prefix}"\n'.encode()
    if backend_obj[0] != expected_backend:
        return {"error": "backend is not restricted to this run"}, 400

    tag = f"lab-cleanup-{run_id}"
    marker_path = f"{prefix}/shutdown.json"
    for _ in range(4):
        obj = get_obj(marker_path)
        if obj:
            try:
                marker = json.loads(obj[0]); generation = obj[1]
            except (ValueError, TypeError):
                return {"error": "cleanup marker is corrupt"}, 500
        else:
            marker, generation = {"run_id": run_id, "attempt": 0, "state": "new"}, None
        builds = backend.list_builds(tag)
        if not builds and marker.get("build_name"):
            exact_build = backend.get_build(marker["build_name"])
            if exact_build:
                builds = [exact_build]
        build = next((b for b in builds if b.get("status") not in _TERMINAL), None)
        if build is None:
            build = next((b for b in builds if b.get("status") == "SUCCESS"), None)
        if build is not None:
            marker.update(state="complete" if build.get("status") == "SUCCESS" else "running",
                          build_name=build.get("name"), build_status=build.get("status"))
            newgen = backend.write_object_cas(marker_path, marker, generation)
            if newgen is None:
                continue
            if build.get("status") != "SUCCESS":
                backend.create_poll_task(run_id, int(marker.get("attempt", 0)))
                return {"state": "running", "build": build.get("name")}, 202
            backend.release_active_lease(run_id)
            return {"state": "complete", "build": build.get("name")}, 200
        if marker.get("state") in ("launching", "running"):
            launched = marker.get("launched_at")
            try:
                age = (now or datetime.now(timezone.utc)) - datetime.fromisoformat(launched)
            except (TypeError, ValueError):
                age = timedelta(seconds=_POLL_SECONDS * 2)
            if age.total_seconds() < _LAUNCH_LEASE_SECONDS:
                backend.create_poll_task(run_id, int(marker.get("attempt", 0)))
                return {"state": "launching"}, 202
        failed = [b for b in builds if b.get("status") in _TERMINAL and b.get("status") != "SUCCESS"]
        attempt = max(int(marker.get("attempt", 0)), len(failed))
        if attempt >= _MAX_ATTEMPTS:
            marker.update(state="failed", attempt=attempt, error="cleanup retry limit reached")
            if backend.write_object_cas(marker_path, marker, generation) is None:
                continue
            return {"error": "cleanup retry limit reached"}, 500
        # Claim an attempt before creating the build. This CAS plus tag reconciliation closes
        # concurrent invocations and the create-build/marker crash window.
        marker.update(state="launching", attempt=attempt + 1,
                      source_generation=src_obj[1], run_id=run_id,
                      launched_at=(now or datetime.now(timezone.utc)).isoformat())
        claimed = backend.write_object_cas(marker_path, marker, generation)
        if claimed is None:
            continue
        try:
            build = backend.create_build(tag, run_id, src_obj[1],
                f"gs://{backend.bucket}/{prefix}/request.json",
                f"gs://{backend.bucket}/{prefix}/terraform.tfvars.json",
                f"gs://{backend.bucket}/{prefix}/backend.hcl")
        except Exception:
            # Keep launch claim; next callback first reconciles by deterministic Cloud Build tag.
            backend.create_poll_task(run_id, attempt + 1)
            return {"state": "launching"}, 202
        marker.update(state="running", build_name=build.get("name"), build_status=build.get("status"))
        if backend.write_object_cas(marker_path, marker, claimed) is None:
            # The build is still discoverable by tag on the next callback.
            pass
        backend.create_poll_task(run_id, attempt + 1)
        return {"state": "running", "build": build.get("name")}, 202
    return {"error": "cleanup state contention; retry"}, 503


def main(request):
    """Cloud Functions Framework HTTP entrypoint."""
    try:
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != {"run_id"}:
            return {"error": "body must contain only run_id"}, 400
        response, status = dispatch(body["run_id"], GoogleBackend(_env()))
        return response, status
    except Exception as exc:  # Cloud Run retry/task delivery observes HTTP 5xx.
        # Keep details out of response/logs because they may contain private API data.
        return {"error": "cleanup dispatch temporarily unavailable"}, 500
