"""Bootstrap the reviewed disposable GKE lab without changing cloud infrastructure."""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import subprocess
import sys
from pathlib import Path
import os

from scripts.local_cluster import ARGO_VERSION, MAX_ARGO_MANIFEST_BYTES

ROOT = Path(__file__).resolve().parents[1]
ARGO_MANIFEST_SHA256 = "7efe2d6bbc03f63623640f1e4198f16c84009d510fb810ef71e56df1b7614ba9"
PROJECT_RE = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
ZONE_RE = re.compile(r"^[a-z]+-[a-z0-9]+[1-9]-[a-z]$")
CLUSTER_RE = re.compile(r"^[a-z][a-z0-9-]{0,22}[a-z0-9]$")


def validate_target(project: str, zone: str, cluster: str) -> None:
    if not isinstance(project, str) or not PROJECT_RE.fullmatch(project):
        raise ValueError("project must be an explicit GCP project ID")
    if not isinstance(zone, str) or not ZONE_RE.fullmatch(zone):
        raise ValueError("zone must be an explicit GCP zone")
    if not isinstance(cluster, str) or not CLUSTER_RE.fullmatch(cluster):
        raise ValueError("cluster must be an explicit GKE cluster name")


def expected_context(project: str, zone: str, cluster: str) -> str:
    validate_target(project, zone, cluster)
    return f"gke_{project}_{zone}_{cluster}"


def bootstrap_commands(project: str, zone: str, cluster: str) -> list[list[str]]:
    """Return the exact gcloud/kubectl commands; each kubectl uses one context."""
    context = expected_context(project, zone, cluster)
    return [
        ["gcloud", "container", "clusters", "get-credentials", cluster,
         f"--zone={zone}", f"--project={project}", "--dns-endpoint"],
        ["kubectl", "config", "current-context"],
        ["kubectl", f"--context={context}", "apply", "-f", "bootstrap/namespaces.yaml"],
        ["kubectl", f"--context={context}", "apply", "--server-side", "-k", "bootstrap/gcp/argo"],
        ["kubectl", f"--context={context}", "rollout", "status", "deploy/argocd-repo-server", "-n", "argocd", "--timeout=180s"],
        ["kubectl", f"--context={context}", "rollout", "status", "deploy/argocd-server", "-n", "argocd", "--timeout=180s"],
        ["kubectl", f"--context={context}", "rollout", "status", "deploy/argocd-redis", "-n", "argocd", "--timeout=180s"],
        ["kubectl", f"--context={context}", "rollout", "status", "statefulset/argocd-application-controller", "-n", "argocd", "--timeout=180s"],
        ["kubectl", f"--context={context}", "apply", "-f", "gitops/project.yaml"],
        ["kubectl", f"--context={context}", "wait", "--for=condition=Ready", "nodes", "--all", "--timeout=240s"],
    ]


def resolve_executable(command: list[str], environment: dict[str, str] | None = None,
                       windows: bool | None = None) -> list[str]:
    """Resolve PATH commands before launching; wrap Windows .cmd tools explicitly."""
    if not command:
        raise ValueError("command must not be empty")
    environment = environment or os.environ
    executable = shutil.which(command[0], path=environment.get("PATH"))
    if executable is None:
        raise FileNotFoundError(f"required executable was not found on PATH: {command[0]}")
    if windows is None:
        windows = os.name == "nt"
    if windows and Path(executable).suffix.lower() in {".cmd", ".bat"}:
        comspec = environment.get("COMSPEC", "cmd.exe")
        invocation = subprocess.list2cmdline([executable, *command[1:]])
        return [comspec, "/d", "/s", "/c", invocation]
    return [executable, *command[1:]]


def validate_manifest_source(manifest_source: str) -> Path:
    path = Path(manifest_source).expanduser().resolve(strict=True)
    if not path.is_file():
        raise ValueError("Argo manifest source must be a file")
    if path.stat().st_size > MAX_ARGO_MANIFEST_BYTES:
        raise ValueError("Argo manifest source exceeds the 2 MiB cap")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != ARGO_MANIFEST_SHA256:
        raise ValueError(f"Argo manifest checksum mismatch: observed {actual}")
    return path


def validate_kubeconfig(kubeconfig: str) -> Path:
    if not isinstance(kubeconfig, str) or not kubeconfig.strip():
        raise ValueError("a dedicated kubeconfig path outside the repository is required")
    path = Path(kubeconfig).expanduser().resolve(strict=False)
    if path.is_relative_to(ROOT):
        raise ValueError("kubeconfig must be outside the repository")
    if path.exists():
        raise ValueError("kubeconfig path already exists; choose a new dedicated file")
    if not path.parent.is_dir():
        raise ValueError("kubeconfig parent directory must already exist")
    return path


def bootstrap(project: str, zone: str, cluster: str, kubeconfig: str,
              manifest_sha256: str = ARGO_MANIFEST_SHA256, manifest_source: str | None = None) -> None:
    validate_target(project, zone, cluster)
    if manifest_sha256 != ARGO_MANIFEST_SHA256:
        raise ValueError("Argo manifest digest does not match the pinned v3.5.3 artifact")
    kubeconfig_path = validate_kubeconfig(kubeconfig)
    if manifest_source:
        source_path = validate_manifest_source(manifest_source)
        target_path = ROOT / "bootstrap" / f"argo-install-{ARGO_VERSION}.yaml"
        shutil.copyfile(source_path, target_path)
    else:
        subprocess.run(
            [sys.executable, "-m", "scripts.local_cluster", "verify-argo", "--sha256", ARGO_MANIFEST_SHA256],
            cwd=ROOT,
            check=True,
        )
    shutil.copyfile(ROOT / "bootstrap" / f"argo-install-{ARGO_VERSION}.yaml",
                    ROOT / "bootstrap" / "gcp" / "argo" / f"argo-install-{ARGO_VERSION}.yaml")
    commands = bootstrap_commands(project, zone, cluster)
    environment = os.environ.copy()
    environment["KUBECONFIG"] = str(kubeconfig_path)
    subprocess.run(resolve_executable(commands[0], environment), cwd=ROOT, check=True, env=environment)
    context_result = subprocess.run(resolve_executable(commands[1], environment), cwd=ROOT, check=True, capture_output=True, text=True, env=environment)
    actual_context = context_result.stdout.strip()
    context = expected_context(project, zone, cluster)
    if actual_context != context:
        raise RuntimeError(f"active context changed unexpectedly: expected {context}, observed {actual_context}")
    for command in commands[2:]:
        subprocess.run(resolve_executable(command, environment), cwd=ROOT, check=True, env=environment)
    print(f"GKE bootstrap complete on exact context {context}; Argo CD controllers are ready.")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    args = sub.add_parser("bootstrap", help="install the pinned small-lab Argo CD profile")
    args.add_argument("--project", required=True)
    args.add_argument("--zone", required=True)
    args.add_argument("--cluster", required=True)
    args.add_argument("--argo-sha256", default=ARGO_MANIFEST_SHA256)
    args.add_argument("--argo-manifest-source", help="optional predownloaded manifest file to verify locally")
    args.add_argument("--kubeconfig", required=True, help="new dedicated kubeconfig path outside this repository")
    parsed = parser.parse_args(argv)
    try:
        bootstrap(parsed.project, parsed.zone, parsed.cluster, parsed.kubeconfig,
                  parsed.argo_sha256, parsed.argo_manifest_source)
        return 0
    except (OSError, subprocess.CalledProcessError, RuntimeError, ValueError) as exc:
        print(f"GKE bootstrap stopped: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
