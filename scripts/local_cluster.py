"""Plan-only kind bootstrap and exact-name teardown helpers."""
from __future__ import annotations

import argparse
import hashlib
import math
import re
from pathlib import Path
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.error import HTTPError

CLUSTER_NAME = "ottawa-fleet-lab"
CONTEXT = f"kind-{CLUSTER_NAME}"
MIN_DOCKER_CPUS = 6
MIN_DOCKER_MEMORY_GIB = 8
KIND_NODE_IMAGE = "kindest/node:v1.35.8@sha256:07b2536e30b803ed61d1677a79df6115f798ce64c80f9e22f6ed45afd09323c0"
ARGO_VERSION = "v3.5.3"
MAX_ARGO_MANIFEST_BYTES = 2 * 1024 * 1024


def can_create_cluster(memory_gib: float, cpus: int) -> bool:
    if isinstance(memory_gib, bool) or isinstance(cpus, bool):
        return False
    if not isinstance(memory_gib, (int, float)) or not math.isfinite(memory_gib):
        return False
    if not isinstance(cpus, int) or cpus <= 0:
        return False
    return memory_gib >= MIN_DOCKER_MEMORY_GIB and cpus >= MIN_DOCKER_CPUS


def validate_deletion_target(target: str, confirmation: str) -> bool:
    return target == CLUSTER_NAME and confirmation == CLUSTER_NAME


def build_kind_config() -> str:
    return f'''kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
- role: control-plane
  image: {KIND_NODE_IMAGE}
- role: worker
  image: {KIND_NODE_IMAGE}
'''


def bootstrap_commands() -> list[str]:
    return [
        f"kind create cluster --name {CLUSTER_NAME} --image {KIND_NODE_IMAGE} --config bootstrap/kind.yaml",
        f"kubectl --context {CONTEXT} apply -f bootstrap/namespaces.yaml",
        f"kubectl --context {CONTEXT} apply --namespace argocd --server-side -f bootstrap/argo-install-{ARGO_VERSION}.yaml",
    ]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="print a no-side-effect bootstrap plan")
    plan.add_argument("--docker-cpus", type=int, required=True)
    plan.add_argument("--docker-memory-gib", type=float, required=True)
    plan.add_argument("--expected-context", required=True)
    delete = sub.add_parser("delete-plan", help="print the exact-name teardown command")
    delete.add_argument("--cluster-name", required=True)
    delete.add_argument("--confirm-name", required=True)
    verify = sub.add_parser("verify-argo", help="download one version-pinned manifest and verify its supplied SHA-256")
    verify.add_argument("--sha256", required=True, help="SHA-256 obtained independently from a reviewed official release artifact")
    args = parser.parse_args(argv)
    if args.command == "plan":
        if args.expected_context != CONTEXT:
            parser.error(f"expected context must be exactly {CONTEXT}")
        if not can_create_cluster(args.docker_memory_gib, args.docker_cpus):
            parser.error(f"Docker needs at least {MIN_DOCKER_CPUS} CPUs and {MIN_DOCKER_MEMORY_GIB} GiB RAM")
        print("PLAN ONLY. This command creates no cluster and changes no context.")
        print(f"First run: python -m scripts.local_cluster verify-argo --sha256 { '<reviewed-64-hex-digest>' }")
        print("\n".join(bootstrap_commands()))
        return 0
    if args.command == "verify-argo":
        if not re.fullmatch(r"[a-f0-9]{64}", args.sha256):
            parser.error("--sha256 must be 64 lowercase hexadecimal characters")
        url = f"https://raw.githubusercontent.com/argoproj/argo-cd/{ARGO_VERSION}/manifests/install.yaml"
        class RejectRedirect(HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise ValueError("manifest URL redirected; download rejected")
        try:
            response = build_opener(RejectRedirect).open(url, timeout=10)
        except HTTPError as exc:
            if 300 <= exc.code < 400:
                parser.error("manifest URL redirected; download rejected")
            raise
        with response:
            if response.geturl() != url or len(response.geturl()) > 2048:
                parser.error("manifest URL redirected; download rejected")
            data = response.read(MAX_ARGO_MANIFEST_BYTES + 1)
        if len(data) > MAX_ARGO_MANIFEST_BYTES:
            parser.error("manifest exceeded 2 MiB cap")
        actual = hashlib.sha256(data).hexdigest()
        if actual != args.sha256:
            parser.error(f"manifest checksum mismatch: expected {args.sha256}, observed {actual}")
        target = Path("bootstrap") / f"argo-install-{ARGO_VERSION}.yaml"
        target.write_bytes(data)
        print(f"Verified official pinned manifest SHA-256 {actual}: {target}")
        return 0
    if not validate_deletion_target(args.cluster_name, args.confirm_name):
        parser.error("deletion requires exact cluster name and matching confirmation")
    print(f"PLAN ONLY. Review active context ({CONTEXT}) and ownership before running:")
    print(f"kind delete cluster --name {CLUSTER_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
