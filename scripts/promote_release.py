"""Validate and render an immutable app chart promotion without external deps."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9./_-]*@sha256:([a-f0-9]{64})$")
SHA_RE = re.compile(r"^[a-f0-9]{40}$")
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
REPO = "https://github.com/ANISHG-26/ottawa-fleet-app.git"
IMAGE_PATHS = {"dbInit": "db-init", "fleetApi": "fleet-api", "rideApi": "ride-api",
               "worker": "assignment-worker", "scenarioRunner": "scenario-runner", "web": "web"}
IMAGE_PATHS_WITH_SIMULATION = {**IMAGE_PATHS, "simulationController": "simulation-controller"}
RUNTIME_FIELDS = {"simulationEnabled", "fleetProfile", "backgroundColor"}


def parse_immutable_image(value: str) -> str:
    match = IMAGE_RE.fullmatch(value or "")
    if not match or set(match.group(1)) == {"0"}:
        raise ValueError("image must use a non-placeholder sha256 digest")
    return value


def parse_chart_version(value: str) -> str:
    if not VERSION_RE.fullmatch(value or ""):
        raise ValueError("chart version must be an exact semantic version")
    return value


def parse_commit_sha(value: str) -> str:
    if not SHA_RE.fullmatch(value or "") or set(value) == {"0"}:
        raise ValueError("source revision must be a full 40-character commit SHA")
    return value


def validate_promotion(promotion: dict) -> dict:
    try:
        chart, source, images, database, rollback = (promotion[k] for k in ("chart", "source", "images", "database", "rollback"))
        if chart.get("repository") != REPO or chart.get("name") != "charts/ottawa-fleet":
            raise ValueError("chart must reference the app-owned Git chart path")
        chart_version = parse_chart_version(chart.get("version"))
        chart_core = tuple(int(part) for part in chart_version.split("-")[0].split("."))
        chart_has_runtime_contract = chart_core > (0, 2, 0) or (chart_core == (0, 2, 0) and "-" not in chart_version)
        if source.get("repository") != REPO:
            raise ValueError("source repository must be the application repository")
        parse_commit_sha(source.get("revision"))
        runtime_present = "runtime" in promotion
        runtime = promotion.get("runtime")
        image_paths = IMAGE_PATHS_WITH_SIMULATION if chart_has_runtime_contract else IMAGE_PATHS
        if not isinstance(images, dict) or set(images) != set(image_paths):
            expected_count = 7 if chart_has_runtime_contract else 6
            raise ValueError(f"chart version {chart_version} requires exactly {expected_count} release images")
        if runtime_present:
            if not chart_has_runtime_contract:
                raise ValueError("runtime settings require chart version 0.2.0 or newer")
            if not isinstance(runtime, dict) or set(runtime) != RUNTIME_FIELDS:
                raise ValueError("runtime must contain exactly simulationEnabled, fleetProfile, and backgroundColor")
            if type(runtime["simulationEnabled"]) is not bool:
                raise ValueError("runtime.simulationEnabled must be a boolean")
            if runtime["fleetProfile"] not in {"default-six", "route20synthetic"}:
                raise ValueError("runtime.fleetProfile must be default-six or route20synthetic")
            if runtime["backgroundColor"] not in {"green", "blue"}:
                raise ValueError("runtime.backgroundColor must be green or blue")
            if runtime["simulationEnabled"] and runtime["fleetProfile"] != "route20synthetic":
                raise ValueError("simulation requires runtime.fleetProfile=route20synthetic")
        for name, image in images.items():
            if not isinstance(image, dict):
                raise ValueError("each image requires immutable reference, source commit, and architecture")
            parse_immutable_image(image.get("reference"))
            expected_repo = f"ghcr.io/anishg-26/ottawa-fleet-app/{image_paths[name]}"
            if image["reference"].rsplit("@sha256:", 1)[0] != expected_repo:
                raise ValueError(f"{name} image repository must match the app release workflow")
            if parse_commit_sha(image.get("sourceCommit")) != source["revision"]:
                raise ValueError("every image sourceCommit must match the pinned chart source revision")
            if image.get("architecture") not in {"amd64", "arm64"}:
                raise ValueError("image architecture must be an explicit supported build architecture")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", database.get("existingSecret", "")):
            raise ValueError("database.existingSecret must reference an externally managed Secret")
        parse_chart_version(rollback.get("previousCompatibleVersion"))
        if rollback.get("migrationBackwardCompatible") is not True:
            raise ValueError("rollback requires verified backward-compatible database migrations")
    except (KeyError, AttributeError, TypeError) as exc:
        raise ValueError(f"incomplete promotion contract: {exc}") from exc
    return promotion


def verify_app_checkout(promotion: dict, checkout: str) -> None:
    """Verify chart version and clean checked-out source correspond to release input."""
    p = validate_promotion(promotion)
    root = Path(checkout).resolve()
    try:
        revision = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], check=True,
                                  capture_output=True, text=True, timeout=5).stdout.strip()
        origin = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], check=True,
                                capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
                               check=True, capture_output=True, text=True, timeout=5).stdout
        chart_file = root / p["chart"]["name"] / "Chart.yaml"
        chart_text = chart_file.read_text(encoding="utf-8")
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"app checkout could not be verified: {exc}") from exc
    if revision != p["source"]["revision"]:
        raise ValueError("app checkout HEAD does not match the pinned source revision")
    accepted_origins = {REPO, "git@github.com:ANISHG-26/ottawa-fleet-app.git"}
    if origin not in accepted_origins:
        raise ValueError("app checkout origin is not the declared application repository")
    if dirty:
        raise ValueError("app checkout has modified or untracked files")
    found = re.search(r"(?m)^version:\s*['\"]?([^\s'\"]+)['\"]?\s*$", chart_text)
    if not found or found.group(1) != p["chart"]["version"]:
        raise ValueError("Chart.yaml version at the pinned checkout does not match the promotion")


def application_manifest(promotion: dict) -> dict:
    p = validate_promotion(promotion)
    params = [{"name": f"images.{name}.repository", "value": image["reference"].rsplit("@sha256:", 1)[0]} for name, image in p["images"].items()]
    params += [{"name": f"images.{name}.digest", "value": "sha256:" + image["reference"].rsplit("@sha256:", 1)[1]} for name, image in p["images"].items()]
    params += [{"name": f"images.{name}.sourceCommit", "value": image["sourceCommit"]} for name, image in p["images"].items()]
    params += [{"name": f"images.{name}.architecture", "value": image["architecture"]} for name, image in p["images"].items()]
    params.append({"name": "database.existingSecret", "value": p["database"]["existingSecret"]})
    if "runtime" in p:
        runtime = p["runtime"]
        params += [
            {"name": "simulation.enabled", "value": str(runtime["simulationEnabled"]).lower()},
            {"name": "simulation.fleetProfile", "value": runtime["fleetProfile"]},
            {"name": "web.backgroundColor", "value": runtime["backgroundColor"]},
        ]
    return {"apiVersion": "argoproj.io/v1alpha1", "kind": "Application", "metadata": {"name": "ottawa-fleet", "namespace": "argocd", "labels": {"platform.ottawa-fleet/owner": "gitops"}},
            "spec": {"project": "ottawa-fleet", "source": {"repoURL": REPO, "targetRevision": p["source"]["revision"],
                         "path": p["chart"]["name"], "helm": {"parameters": params}},
                     "destination": {"server": "https://kubernetes.default.svc", "namespace": "fleet-app"},
                     "syncPolicy": {"automated": {"prune": True, "selfHeal": True}, "syncOptions": ["CreateNamespace=false"]},
                     "info": [{"name": "chart-version", "value": p["chart"]["version"]},
                              {"name": "previous-compatible-version", "value": p["rollback"]["previousCompatibleVersion"]}]}}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("promotion", help="JSON promotion descriptor")
    parser.add_argument("--app-checkout", required=True, help="clean local app repository checked out at its release commit")
    parser.add_argument("--output", required=True, help="JSON Kubernetes Application manifest")
    args = parser.parse_args(argv)
    try:
        with open(args.promotion, encoding="utf-8") as src:
            promotion = json.load(src)
        verify_app_checkout(promotion, args.app_checkout)
        rendered = application_manifest(promotion)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as dst:
            json.dump(rendered, dst, indent=2)
            dst.write("\n")
        print(f"Promotion manifest prepared: {args.output}; no cluster changes made")
        return 0
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Promotion rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
