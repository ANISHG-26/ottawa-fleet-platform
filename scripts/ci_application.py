"""Resolve and deploy the newest trusted immutable application release."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import base64
import hashlib
import ipaddress
import json
import os
import re
import subprocess
import time
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from scripts.promote_release import (IMAGE_PATHS_WITH_SIMULATION as IMAGE_PATHS,
                                     parse_chart_version, parse_commit_sha,
                                     parse_immutable_image)

APP = "ANISHG-26/ottawa-fleet-app"
REPO = "https://github.com/ANISHG-26/ottawa-fleet-app.git"
GHCR = "ghcr.io/anishg-26/ottawa-fleet-app"
MINIMUM = (0, 2, 1)
ACCEPT = ",".join((
    "application/vnd.oci.image.index.v1+json", "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.docker.distribution.manifest.v2+json",
))
TAG_RE = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def _version(tag: str):
    match = TAG_RE.fullmatch(tag or "")
    return tuple(map(int, match.groups())) if match else None


def select_latest_stable(tags: list[dict]) -> dict:
    candidates = []
    for tag in tags:
        version = _version(tag.get("name")) if isinstance(tag, dict) else None
        if version and version >= MINIMUM:
            candidates.append((version, tag))
    if not candidates:
        raise ValueError("no stable application tag at or above v0.2.1 is available")
    selected = max(candidates, key=lambda item: item[0])[1]
    if not isinstance(selected.get("sha"), str) or not re.fullmatch(r"[a-f0-9]{40}", selected["sha"]):
        raise ValueError(f"latest stable application tag {selected.get('name')} has no exact Git SHA")
    return selected


def validate_release_run(run: dict, tag: str, sha: str) -> None:
    if (not isinstance(run, dict) or run.get("event") != "push" or
            run.get("status") != "completed" or run.get("conclusion") != "success" or
            run.get("head_sha") != sha or run.get("head_branch") != tag):
        raise ValueError(f"latest stable tag {tag} has no successful trusted release.yml push run for its exact SHA")


def _read_json(url: str, *, headers=None, opener=urlopen, limit=2_000_000):
    req = Request(url, headers=headers or {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with opener(req, timeout=20) as response:
        raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("public release response exceeded the bounded read size")
        return json.loads(raw), response.headers


def _github_json(api: str, path: str, *, opener=urlopen):
    result, _ = _read_json(f"{api.rstrip('/')}/{path.lstrip('/')}", opener=opener)
    return result


def fetch_tags(api="https://api.github.com", *, opener=urlopen):
    tags = []
    for page in range(1, 11):
        batch = _github_json(api, f"repos/{APP}/tags?per_page=100&page={page}", opener=opener)
        if not isinstance(batch, list):
            raise ValueError("GitHub tags response was malformed")
        if not batch:
            break
        for item in batch:
            tags.append({"name": item.get("name"), "sha": item.get("commit", {}).get("sha")})
        if len(batch) < 100:
            break
        if page == 10:
            raise ValueError("public GitHub tag pagination reached its 1,000-tag safety cap")
    return tags


def resolve_tag_commit(tag: dict, api="https://api.github.com", *, opener=urlopen):
    ref = _github_json(api, f"repos/{APP}/git/ref/tags/{quote(tag['name'], safe='')}", opener=opener)
    obj = ref.get("object", {}) if isinstance(ref, dict) else {}
    for _ in range(5):
        sha = obj.get("sha")
        if obj.get("type") != "tag":
            break
        annotated = _github_json(api, f"repos/{APP}/git/tags/{sha}", opener=opener)
        obj = annotated.get("object", {})
    if obj.get("type") == "tag":
        raise ValueError(f"annotated tag {tag['name']} exceeds the bounded tag-depth limit")
    commit = obj.get("sha")
    if obj.get("type") != "commit":
        raise ValueError(f"GitHub tag {tag['name']} did not resolve to a commit object")
    try:
        parse_commit_sha(commit)
    except ValueError as exc:
        raise ValueError(f"GitHub tag {tag['name']} did not resolve to an exact commit SHA")
    return {"name": tag["name"], "sha": commit}


def latest_release(api="https://api.github.com", *, opener=urlopen):
    tag = resolve_tag_commit(select_latest_stable(fetch_tags(api, opener=opener)), api, opener=opener)
    run_list = _github_json(api, f"repos/{APP}/actions/workflows/release.yml/runs?event=push&branch={tag['name']}&per_page=100", opener=opener)
    runs = run_list.get("workflow_runs", []) if isinstance(run_list, dict) else []
    matching = [run for run in runs if isinstance(run, dict) and run.get("head_branch") == tag["name"] and run.get("head_sha") == tag["sha"]]
    if not matching:
        raise ValueError(f"latest stable tag {tag['name']} has no trusted release.yml run for its exact SHA")
    matching.sort(key=lambda run: run.get("run_number", 0), reverse=True)
    validate_release_run(matching[0], tag["name"], tag["sha"])
    return tag, matching[0]


def _registry_get(repo: str, path: str, token: str, *, opener=urlopen):
    req = Request(f"https://ghcr.io/v2/{repo}/{path}", headers={"Authorization": f"Bearer {token}", "Accept": ACCEPT})
    with opener(req, timeout=20) as response:
        raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("registry manifest exceeded the bounded read size")
        return json.loads(raw), response.headers, raw


def inspect_image(name: str, tag: str, sha: str, *, opener=urlopen):
    path = IMAGE_PATHS[name]
    repo = f"anishg-26/ottawa-fleet-app/{path}"
    token_body, _ = _read_json("https://ghcr.io/token?" + urlencode({"service": "ghcr.io", "scope": f"repository:{repo}:pull"}),
                               headers={"Accept": "application/json"}, opener=opener, limit=100_000)
    token = token_body.get("token") if isinstance(token_body, dict) else None
    if not isinstance(token, str) or not token:
        raise ValueError(f"public registry did not issue anonymous pull access for {name}")
    manifest, headers, raw = _registry_get(repo, f"manifests/{tag}", token, opener=opener)
    release_digest = headers.get("Docker-Content-Digest")
    if (not isinstance(release_digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", release_digest) or
            "sha256:" + hashlib.sha256(raw).hexdigest() != release_digest):
        raise ValueError(f"{name} release tag did not resolve to an immutable manifest digest")
    try:
        parse_immutable_image(f"{GHCR}/{path}@{release_digest}")
    except ValueError as exc:
        raise ValueError(f"{name} release tag resolved to a placeholder digest") from exc
    platform_digest = release_digest
    descriptors = manifest.get("manifests") if isinstance(manifest, dict) else None
    if descriptors is not None:
        variants = [x for x in descriptors if x.get("platform", {}).get("os") == "linux" and
                    x.get("platform", {}).get("architecture") == "amd64"]
        if len(variants) != 1:
            raise ValueError(f"{name} release index must contain exactly one linux/amd64 image")
        platform_digest = variants[0].get("digest")
        if not isinstance(platform_digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", platform_digest):
            raise ValueError(f"{name} linux/amd64 manifest digest is invalid")
        manifest, _, raw = _registry_get(repo, f"manifests/{platform_digest}", token, opener=opener)
        if "sha256:" + hashlib.sha256(raw).hexdigest() != platform_digest:
            raise ValueError(f"{name} linux/amd64 manifest bytes do not match their descriptor digest")
    config_desc = manifest.get("config", {}) if isinstance(manifest, dict) else {}
    config_digest = config_desc.get("digest")
    if not isinstance(config_digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", config_digest):
        raise ValueError(f"{name} manifest has no valid config digest")
    config, _, raw = _registry_get(repo, f"blobs/{config_digest}", token, opener=opener)
    if "sha256:" + hashlib.sha256(raw).hexdigest() != config_digest:
        raise ValueError(f"{name} image config bytes do not match their descriptor digest")
    labels = config.get("config", {}).get("Labels", {}) if isinstance(config, dict) else {}
    if (config.get("architecture") != "amd64" or config.get("os") != "linux" or
            labels.get("org.opencontainers.image.revision") != sha or
            labels.get("org.opencontainers.image.version") != tag or
            labels.get("org.opencontainers.image.source") != "https://github.com/ANISHG-26/ottawa-fleet-app"):
        raise ValueError(f"{name} OCI architecture, source revision, or version does not match {tag}")
    return {"reference": f"{GHCR}/{path}@{release_digest}", "sourceCommit": sha,
            "architecture": "amd64", "platformDigest": platform_digest}


def build_application(tag: str, sha: str, digests: dict, template: dict, chart_text: str) -> dict:
    version = _version(tag)
    if version is None or version < MINIMUM:
        raise ValueError("selected application tag is below the stable release floor")
    parse_commit_sha(sha)
    chart_match = re.search(r"(?m)^version:\s*['\"]?([^\s'\"]+)['\"]?\s*$", chart_text)
    chart_version = parse_chart_version(chart_match.group(1) if chart_match else "")
    if chart_version != tag[1:]:
        raise ValueError("app Helm chart version at the selected SHA does not match the selected tag")
    if set(digests) != set(IMAGE_PATHS):
        raise ValueError("release must provide exactly the seven expected app images")
    app = json.loads(json.dumps(template))
    app["spec"]["source"]["repoURL"] = REPO
    app["spec"]["source"]["targetRevision"] = sha
    params = []
    for name, path in IMAGE_PATHS.items():
        image = digests[name]
        expected = f"{GHCR}/{path}"
        ref = image.get("reference", "")
        match = re.fullmatch(re.escape(expected) + r"@(sha256:[a-f0-9]{64})", ref)
        if not match or image.get("sourceCommit") != sha or image.get("architecture") != "amd64":
            raise ValueError(f"{name} image identity does not match the selected release")
        params += [
            {"name": f"images.{name}.repository", "value": expected},
            {"name": f"images.{name}.digest", "value": match.group(1)},
            {"name": f"images.{name}.sourceCommit", "value": sha},
            {"name": f"images.{name}.architecture", "value": "amd64"},
        ]
    params += [
        {"name": "database.existingSecret", "value": "ottawa-fleet-database"},
        {"name": "simulation.enabled", "value": "true"},
        {"name": "simulation.fleetProfile", "value": "route20synthetic"},
        {"name": "web.backgroundColor", "value": "green"},
    ]
    app["spec"]["source"]["path"] = "charts/ottawa-fleet"
    app["spec"]["source"]["helm"]["parameters"] = params
    app["spec"]["info"] = [{"name": "chart-version", "value": chart_version}]
    return app


def resolve_application(template_path, *, api="https://api.github.com", opener=urlopen):
    tag, run = latest_release(api, opener=opener)
    version = tag["name"][1:]
    chart_url = f"https://raw.githubusercontent.com/{APP}/{tag['sha']}/charts/ottawa-fleet/Chart.yaml"
    request = Request(chart_url, headers={"Accept": "text/plain"})
    with opener(request, timeout=20) as response:
        chart_text = response.read(100_001).decode("utf-8")
    if len(chart_text) > 100_000:
        raise ValueError("Chart.yaml exceeded the bounded read size")
    images = {name: inspect_image(name, tag["name"], tag["sha"], opener=opener) for name in IMAGE_PATHS}
    with open(template_path, encoding="utf-8") as source:
        template = json.load(source)
    app = build_application(tag["name"], tag["sha"], images, template, chart_text)
    return app, {"tag": tag["name"], "sha": tag["sha"], "run_id": run.get("id"),
                 "digests": {key: value["reference"].rsplit("@", 1)[1] for key, value in images.items()}}


def _run(command, *, runner=subprocess.run, cwd=None, input_text=None, timeout=60, env=None):
    try:
        result = runner(command, cwd=cwd, text=True, input=input_text, capture_output=True,
                        check=False, timeout=timeout, env=env)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError(f"application deployment command failed ({command[0]})") from None
    if result.returncode:
        raise RuntimeError(f"application deployment command failed ({command[0]}, exit {result.returncode})")
    return result.stdout


def deploy(*, project: str, zone: str, cluster: str, kubeconfig: str, expires_at: str,
           secret_values: dict, template_path, runner=subprocess.run, opener=urlopen,
           sleep=time.sleep, now=lambda: datetime.now(timezone.utc)):
    from scripts.gcp_lab import expected_context
    context = expected_context(project, zone, cluster)
    deadline = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    def remaining():
        seconds = (deadline - now()).total_seconds()
        if seconds <= 0:
            raise RuntimeError("fixed lab expiry elapsed before application deployment step")
        return seconds
    remaining()
    app, release = resolve_application(template_path, opener=opener)
    env = dict(os.environ)
    env["KUBECONFIG"] = kubeconfig
    base = ["kubectl", f"--context={context}"]
    readiness_deadline = None
    def kubectl(args, *, data=None, timeout=60):
        seconds = remaining()
        if readiness_deadline is not None:
            readiness_left = (readiness_deadline - now()).total_seconds()
            if readiness_left <= 0:
                raise RuntimeError("Argo application did not become ready within the ten-minute CI wait bound")
            seconds = min(seconds, readiness_left)
        return _run([*base, *args], runner=runner, cwd=template_path.parents[3], input_text=data,
                    timeout=min(timeout, max(1, int(seconds))), env=env)
    # Use the existing database Secret contract. JSON is valid YAML; never put credential values in argv/output.
    password = secret_values.get("database_password")
    if not isinstance(password, str) or len(password) < 32:
        raise ValueError("the run's private Terraform inputs do not contain the database password")
    db_enabled = secret_values.get("cloudsql_enabled")
    secret = None
    remaining()
    if db_enabled:
        outputs = json.loads(_run(["terraform", "output", "-json"], runner=runner, cwd=template_path.parents[3] / "terraform" / "lab", timeout=30))
        def output(key):
            item = outputs.get(key, {})
            return item.get("value") if isinstance(item, dict) else None
        if (output("cloudsql_enabled") is not True or output("cluster_name") != cluster or
                output("cluster_location") != zone or output("cloudsql_instance_name") != f"{cluster}-postgres"):
            raise ValueError("Terraform outputs do not identify this exact lab run's cluster and database")
        ip, database, username = output("cloudsql_private_ip"), output("cloudsql_database_name"), output("cloudsql_user_name")
        if not all(isinstance(x, str) and x for x in (ip, database, username)):
            raise ValueError("Terraform outputs for the already-applied private database are incomplete")
        try:
            parsed_ip = ipaddress.ip_address(ip)
        except ValueError as exc:
            raise ValueError("Terraform private database address is not a valid IP address") from exc
        if parsed_ip.version != 4 or not parsed_ip.is_private:
            raise ValueError("Terraform database address must be a private IPv4 address")
        from urllib.parse import quote
        url = f"postgresql://{quote(username, safe='')}:{quote(password, safe='')}@{ip}:5432/{quote(database, safe='')}?sslmode=require"
        secret = {"apiVersion": "v1", "kind": "Secret", "metadata": {"name": "ottawa-fleet-database", "namespace": "fleet-app"},
                  "type": "Opaque", "data": {"DATABASE_URL": base64.b64encode(url.encode()).decode()}}
    else:
        raise ValueError("automatic app deployment requires Cloud SQL for the private database")
    # The namespace is owned by bootstrap; apply remains idempotent and checks ownership.
    kubectl(["apply", "-f", "bootstrap/namespaces.yaml"])
    kubectl(["apply", "-f", "-"], data=json.dumps(secret, separators=(",", ":")))
    kubectl(["apply", "-f", "-"], data=json.dumps(app, separators=(",", ":")))
    app_name = "ottawa-fleet"
    readiness_deadline = min(deadline, now() + timedelta(minutes=10))
    def wait_remaining():
        remaining()
        seconds = (readiness_deadline - now()).total_seconds()
        if seconds <= 0:
            raise RuntimeError("Argo application did not become ready within the ten-minute CI wait bound")
        return seconds
    while True:
        wait_remaining()
        observed = json.loads(kubectl(["get", "application", app_name, "-n", "argocd", "-o", "json"], timeout=30))
        status = observed.get("status", {})
        operation = status.get("operationState", {})
        if operation.get("phase") in {"Failed", "Error"}:
            raise RuntimeError("Argo application sync or migration hook failed")
        resources = operation.get("syncResult", {}).get("resources", [])
        migration_succeeded = any(resource.get("kind") == "Job" and
                                  str(resource.get("name", "")).startswith("db-init-") and
                                  resource.get("hookPhase") == "Succeeded" for resource in resources)
        if (status.get("sync", {}).get("status") == "Synced" and
                status.get("sync", {}).get("revision") == release["sha"] and
                status.get("health", {}).get("status") == "Healthy" and
                operation.get("phase") == "Succeeded" and migration_succeeded and
                operation.get("syncResult", {}).get("revision") == release["sha"]):
            break
        sleep(min(10, max(1, wait_remaining())))
    deployments = ("fleet-api", "ride-api", "assignment-worker", "simulation-controller", "web")
    for name in deployments:
        timeout = max(1, int(wait_remaining()))
        kubectl(["wait", "--for=condition=Available", f"deployment/{name}",
                 "-n", "fleet-app", f"--timeout={timeout}s"], timeout=timeout)
    # Read-only probes through the Kubernetes service proxy exercise the release
    # without opening a tunnel, creating data, or starting a process in a pod.
    def probe(path):
        wait_remaining()
        return json.loads(kubectl(["get", "--raw", path], timeout=20))
    runtime = probe("/api/v1/namespaces/fleet-app/services/http:web:8080/proxy/runtime-config.json")
    fleet = probe("/api/v1/namespaces/fleet-app/services/http:fleet-api:8080/proxy/v1/fleet?limit=20")
    route = probe("/api/v1/namespaces/fleet-app/services/http:simulation-controller:8083/proxy/v2/simulation/routes/lansdowne-centretown-v1")
    ride = probe("/api/v1/namespaces/fleet-app/services/http:ride-api:8081/proxy/readyz")
    if runtime.get("backgroundColor") != "green":
        raise RuntimeError("web runtime configuration did not report the green release marker")
    if not isinstance(fleet.get("items"), list) or len(fleet["items"]) != 20:
        raise RuntimeError("read-only Fleet API probe did not return the 20-vehicle synthetic profile")
    if not isinstance(route.get("points"), list) or len(route["points"]) != 21:
        raise RuntimeError("simulation route probe did not return the expected 21 route points")
    if ride.get("status") != "ok":
        raise RuntimeError("Ride API readiness probe failed")
    return release
