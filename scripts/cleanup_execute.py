"""Cloud Build worker: destroy the exact CI run and verify its inventory is gone."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from scripts.lab_cleanup import validate_cleanup_request


_RUN_ID = re.compile(r"^[0-9]{8,13}$")
_TF_VERSION = "1.8.4"
_TF_SHA256 = {
    "amd64": "12167574ae0deb219a1008bd4c15ff13dac7198d57870f48433d53fe2b0b28c4",
    "arm64": "76668e7742ee8f815fe6de28c8b84507e6171b26966426c2eb8eea8e64fe2f33",
}


def run(args: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(args, cwd=cwd, env=env, check=True, text=True, capture_output=True)
    return result.stdout


def download_private(uri: str, dest: Path) -> None:
    if not uri.startswith("gs://"):
        raise ValueError("private input URI must use gs://")
    run(["gcloud", "storage", "cp", uri, str(dest)])


def save_gateway_inventory(*, bucket: str, prefix: str, network: str, project: str,
                           work: Path, command=run, gateway_ips: set[str] | None = None) -> set[str]:
    """Persist exact gateway forwarding-rule identities before service deletion."""
    uri = f"gs://{bucket}/{prefix}/runowned-resources.json"
    path = work / "runowned-resources.json"
    probe = subprocess.run(["gcloud", "storage", "cp", uri, str(path)], text=True,
                           capture_output=True, check=False)
    if probe.returncode == 0:
        inventory = json.loads(path.read_text())
        if inventory.get("retained_network") != network:
            raise RuntimeError("run-owned resource inventory targets a different retained network")
        return {item["selfLink"] for item in inventory.get("gateway_forwarding_rules", [])}
    missing_markers = ("No URLs matched", "matched no objects or files", "NotFound", "404", "does not exist")
    if not any(marker.lower() in ((probe.stderr or "") + (probe.stdout or "")).lower()
               for marker in missing_markers):
        raise RuntimeError("could not read prior run-owned resource inventory")
    ips = gateway_ips or set()
    network_obj = json.loads(command(["gcloud", "compute", "networks", "describe", network,
                                      "--project", project, "--format=json"]) or "{}")
    network_link = network_obj.get("selfLink", f"projects/{project}/global/networks/{network}")
    rules = json.loads(command(["gcloud", "compute", "forwarding-rules", "list", "--project", project,
                                "--format=json"]) or "[]")
    if not ips and any(rule.get("network") == network_link for rule in rules):
        raise RuntimeError("cannot identify gateway forwarding rules without exact gateway IPs")
    owned = [{key: rule[key] for key in ("name", "selfLink", "IPAddress", "backendService") if key in rule}
             for rule in rules if rule.get("IPAddress") in ips]
    inventory = {"retained_network": network, "gateway_forwarding_rules": owned}
    path.write_text(json.dumps(inventory, sort_keys=True) + "\n", encoding="utf-8")
    upload = subprocess.run(["gcloud", "storage", "cp", "--if-generation-match=0", str(path), uri],
                            text=True, capture_output=True, check=False)
    if upload.returncode:
        # A concurrent retry may have won the immutable write. Accept only a readable object.
        existing = subprocess.run(["gcloud", "storage", "cp", uri, str(path)], text=True,
                                  capture_output=True, check=False)
        if existing.returncode:
            raise RuntimeError("could not persist or reconcile run-owned resource inventory")
        inventory = json.loads(path.read_text())
    return {item["selfLink"] for item in inventory.get("gateway_forwarding_rules", [])}


def _service_url(cluster_description: dict) -> str:
    endpoint = (cluster_description.get("controlPlaneEndpointsConfig", {})
                .get("dnsEndpointConfig", {}).get("endpoint"))
    if not isinstance(endpoint, str) or not endpoint:
        raise RuntimeError("GKE DNS endpoint is unavailable for gateway cleanup")
    if not endpoint.startswith("https://"):
        endpoint = "https://" + endpoint
    return endpoint.rstrip("/") + "/api/v1/namespaces/fleet-gateway/services/fleet-gateway"


def _kube_request(url: str, token: str, method: str = "GET", opener=urlopen) -> dict | None:
    req = Request(url, data=b"{}" if method == "DELETE" else None, method=method,
                  headers={"Authorization": f"Bearer {token}",
                           "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with opener(req, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def delete_gateway_service(cluster_description: dict, *, before_delete, command=run, opener=urlopen) -> set[str]:
    """Delete the exact gateway Service through GKE's authenticated DNS endpoint."""
    token = command(["gcloud", "auth", "print-access-token"]).strip()
    if not token:
        raise RuntimeError("could not obtain cleanup identity token")
    url = _service_url(cluster_description)
    service = _kube_request(url, token, opener=opener)
    if service is None:
        before_delete(set())
        return set()
    ips = {item["ip"] for item in service.get("status", {}).get("loadBalancer", {}).get("ingress", [])
           if isinstance(item.get("ip"), str) and item["ip"]}
    before_delete(ips)
    _kube_request(url, token, method="DELETE", opener=opener)
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        if _kube_request(url, token, opener=opener) is None:
            return ips
        time.sleep(5)
    raise RuntimeError("gateway Service and load balancer did not finish deletion within five minutes")


def install_terraform(work: Path) -> Path:
    """Fetch Terraform 1.8.4 and verify the reviewed official archive checksum."""
    import platform
    machine = platform.machine().lower()
    arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(machine)
    if arch is None:
        raise RuntimeError("unsupported cleanup worker architecture")
    platform_name = "linux"
    stem = f"terraform_{_TF_VERSION}_{platform_name}_{arch}"
    base = f"https://releases.hashicorp.com/terraform/{_TF_VERSION}"
    with urlopen(f"{base}/{stem}.zip", timeout=90) as response:
        archive = response.read()
    if hashlib.sha256(archive).hexdigest() != _TF_SHA256[arch]:
        raise RuntimeError("Terraform archive checksum validation failed")
    import zipfile
    with zipfile.ZipFile(__import__("io").BytesIO(archive)) as zf:
        info = zf.getinfo("terraform")
        if info.file_size > 150_000_000:
            raise RuntimeError("unexpected Terraform binary size")
        target = work / "terraform"
        target.write_bytes(zf.read(info))
    target.chmod(0o755)
    return target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-uri", required=True)
    parser.add_argument("--tfvars-uri", required=True)
    parser.add_argument("--backend-uri", required=True)
    args = parser.parse_args()
    project = os.environ["EXPECTED_PROJECT"]
    bucket = os.environ["EXPECTED_BUCKET"]
    retained_network = os.environ["EXPECTED_RETAINED_NETWORK"]
    with tempfile.TemporaryDirectory(prefix="lab-cleanup-") as temp:
        work = Path(temp)
        req_path, vars_path, backend_path = (work / name for name in
            ("request.json", "terraform.tfvars.json", "backend.hcl"))
        print("[cleanup] stage=inputs", file=sys.stderr, flush=True)
        download_private(args.request_uri, req_path)
        download_private(args.tfvars_uri, vars_path)
        download_private(args.backend_uri, backend_path)
        request = validate_cleanup_request(json.loads(req_path.read_text()))
        run_id = request["run_id"]
        if not _RUN_ID.fullmatch(run_id) or request["cluster_name"] != f"fleet-lab-r{run_id}":
            raise ValueError("request does not identify an exact CI run")
        tfvars = json.loads(vars_path.read_text())
        prefix = f"gcp-lab/runs/{run_id}"
        if (tfvars.get("project_id") != project or tfvars.get("cluster_name") != request["cluster_name"] or
                tfvars.get("retained_network_name") != retained_network or
                backend_path.read_text() != f'bucket = "{bucket}"\nprefix = "{prefix}"\n'):
            raise ValueError("private Terraform inputs do not match the exact CI run")
        root = Path(__file__).resolve().parents[1] / "terraform" / "lab"
        print("[cleanup] stage=terraform-install", file=sys.stderr, flush=True)
        terraform = install_terraform(work)
        env = dict(os.environ, TF_IN_AUTOMATION="1", TF_INPUT="0")
        print("[cleanup] stage=terraform-init", file=sys.stderr, flush=True)
        run([str(terraform), "init", "-input=false", f"-backend-config={backend_path}"], cwd=root, env=env)
        # Remove the run's public gateway Service first so its external load balancer
        # begins deletion while the cluster and its network remain available.
        print("[cleanup] stage=gateway-cleanup", file=sys.stderr, flush=True)
        try:
            cluster_description = json.loads(run(["gcloud", "container", "clusters", "describe",
                request["cluster_name"], "--project", project, "--zone", tfvars["zone"], "--format=json"]))
        except subprocess.CalledProcessError as exc:
            detail = (exc.stdout or "") + (exc.stderr or "")
            if "NOT_FOUND" not in detail and "was not found" not in detail and "not found" not in detail.lower():
                raise
            gateway_rule_links = save_gateway_inventory(bucket=bucket, prefix=prefix,
                network=retained_network, project=project, work=work,
                gateway_ips=set())
        else:
            inventory = {}
            def persist_gateway_inventory(ips):
                inventory["links"] = save_gateway_inventory(bucket=bucket, prefix=prefix,
                    network=retained_network, project=project, work=work, gateway_ips=ips)
            delete_gateway_service(cluster_description, before_delete=persist_gateway_inventory)
            gateway_rule_links = inventory["links"]
        print("[cleanup] stage=terraform-destroy", file=sys.stderr, flush=True)
        run([str(terraform), "destroy", "-auto-approve", "-input=false",
             f"-var-file={vars_path}"], cwd=root, env=env)
        print("[cleanup] stage=verify-absent", file=sys.stderr, flush=True)
        verify_absent(project, request["cluster_name"], tfvars["zone"], run, gateway_rule_links)
    return 0


def verify_absent(project: str, cluster: str, zone: str, command=run,
                  gateway_rule_links: set[str] | None = None) -> None:
    """Fail the Cloud Build unless run-owned compute and SQL inventory is absent."""
    try:
        command(["gcloud", "container", "clusters", "describe", cluster, "--project", project,
                 "--zone", zone, "--format=json"])
        raise RuntimeError("run-owned GKE cluster still exists after destroy")
    except subprocess.CalledProcessError as exc:
        # Not-found is the expected inventory outcome; other API errors remain failures.
        combined = (exc.stdout or "") + (exc.stderr or "")
        if "NOT_FOUND" not in combined and "Not found" not in combined and "was not found" not in combined:
            raise
    sql = command(["gcloud", "sql", "instances", "list", "--project", project,
                   "--filter", f"name={cluster}-postgres", "--format=json"])
    if json.loads(sql or "[]"):
        raise RuntimeError("run-owned Cloud SQL instance still exists")
    routers = command(["gcloud", "compute", "routers", "list", "--project", project,
                       "--filter", f"name={cluster}-router", "--format=json"])
    if json.loads(routers or "[]"):
        raise RuntimeError("run-owned Cloud Router/NAT still exists")
    # GKE may abbreviate generated disk names. Its reserved ownership labels
    # identify the exact cluster and location without relying on that prefix.
    disks = json.loads(command(["gcloud", "compute", "disks", "list", "--project", project,
                                "--format=json"]) or "[]")
    if any(disk.get("labels", {}).get("goog-k8s-cluster-name") == cluster and
           disk.get("labels", {}).get("goog-k8s-cluster-location") == zone
           for disk in disks):
        raise RuntimeError("run-owned disks still exist")
    inventory_commands = (
        (["gcloud", "compute", "disks", "list"], f"^(gke-{cluster}-|{cluster}-)", "disks"),
        (["gcloud", "compute", "forwarding-rules", "list"], f"^{cluster}-", "forwarding-rules"),
        (["gcloud", "compute", "networks", "subnets", "list"], f"^{cluster}-subnet$", "subnetworks"),
    )
    for command_prefix, pattern, kind in inventory_commands:
        listing = command(command_prefix + ["--project", project,
                           "--filter", f"name~{pattern}", "--format=json"])
        if json.loads(listing or "[]"):
            raise RuntimeError(f"run-owned {kind} still exist")
    if gateway_rule_links:
        rules = json.loads(command(["gcloud", "compute", "forwarding-rules", "list", "--project", project,
                                    "--format=json"]) or "[]")
        leftovers = [rule for rule in rules if rule.get("selfLink") in gateway_rule_links]
        if leftovers:
            raise RuntimeError("gateway load-balancer forwarding rules still exist")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"cleanup failed: {type(exc).__name__}", file=sys.stderr)
        sys.exit(1)
