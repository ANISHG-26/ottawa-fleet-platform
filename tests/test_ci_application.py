import unittest
from pathlib import Path
import hashlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from scripts.ci_application import (select_latest_stable, validate_release_run, build_application,
                                    IMAGE_PATHS, GHCR, inspect_image, fetch_tags, resolve_tag_commit, deploy)
from scripts.ci_application import _run
import subprocess

class StableReleaseTests(unittest.TestCase):
    def test_selects_highest_semver_stable_at_or_above_floor(self):
        tags = [{"name": value, "sha": "a" * 40} for value in ["v0.2.1", "v1.0.0-rc.1", "v0.9.0", "v0.10.0", "v0.2.0"]]
        self.assertEqual(select_latest_stable(tags)["name"], "v0.10.0")

    def test_no_stable_floor_or_failed_latest_run_rejects_without_fallback(self):
        with self.assertRaises(ValueError):
            select_latest_stable([{"name": "v0.2.0", "sha": "a" * 40}, {"name": "v1.0.0-rc.1", "sha": "b" * 40}])
        with self.assertRaisesRegex(ValueError, "v0.10.0"):
            select_latest_stable([{"name": "v0.9.0", "sha": "a" * 40}, {"name": "v0.10.0", "sha": None}])
        with self.assertRaises(ValueError):
            validate_release_run({"event": "push", "status": "completed", "conclusion": "failure", "head_sha": "a" * 40}, "v0.10.0", "a" * 40)

    def test_latest_failed_release_run_does_not_fall_back_to_older_success(self):
        from scripts.ci_application import latest_release
        class Response:
            headers = {}
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, *_): return self.body
        selected_sha = "a" * 40
        selected_tag_object = "b" * 40
        queried = []
        def opener(request, timeout):
            url = request.full_url
            queried.append(url)
            if "/tags?" in url:
                return Response(json.dumps([
                    {"name": "v0.10.0", "commit": {"sha": selected_tag_object}},
                    {"name": "v0.9.0", "commit": {"sha": "c" * 40}},
                ]).encode())
            if "/git/ref/tags/v0.10.0" in url:
                return Response(json.dumps({"object": {"sha": selected_tag_object, "type": "tag"}}).encode())
            if f"/git/tags/{selected_tag_object}" in url:
                return Response(json.dumps({"object": {"sha": selected_sha, "type": "commit"}}).encode())
            if "/actions/workflows/release.yml/runs" in url:
                return Response(json.dumps({"workflow_runs": [{"id": 99999999, "run_number": 12, "event": "push",
                    "status": "completed", "conclusion": "failure", "head_branch": "v0.10.0", "head_sha": selected_sha}]}).encode())
            raise AssertionError(url)
        with self.assertRaisesRegex(ValueError, "v0.10.0"):
            latest_release(opener=opener)
        self.assertTrue(any("branch=v0.10.0" in url for url in queried))
        self.assertFalse(any("branch=v0.9.0" in url for url in queried))

    def test_application_is_exactly_pinned_and_drops_unverified_rollback_claim(self):
        template = __import__("json").loads((Path(__file__).resolve().parents[1] / "gitops/environments/lab/application.json").read_text())
        sha = "a" * 40
        tag_object_sha = "b" * 40
        images = {key: {"reference": f"{GHCR}/{path}@sha256:{i:064x}", "sourceCommit": sha, "architecture": "amd64"}
                  for i, (key, path) in enumerate(IMAGE_PATHS.items(), start=1)}
        app = build_application("v0.2.1", sha, images, template, "apiVersion: v2\nversion: 0.2.1\n")
        self.assertEqual(app["spec"]["source"]["targetRevision"], sha)
        self.assertEqual(len(app["spec"]["source"]["helm"]["parameters"]), 32)
        params = {p["name"]: p["value"] for p in app["spec"]["source"]["helm"]["parameters"]}
        self.assertEqual(params["simulation.enabled"], "true")
        self.assertEqual(params["simulation.fleetProfile"], "route20synthetic")
        self.assertEqual(params["web.backgroundColor"], "green")
        self.assertEqual(app["spec"]["info"], [{"name": "chart-version", "value": "0.2.1"}])

    def test_release_requires_exact_seven_images_and_matching_chart_version(self):
        template = {"spec": {"source": {"helm": {"parameters": []}}}}
        sha = "a" * 40
        images = {key: {"reference": f"{GHCR}/{path}@sha256:{i:064x}", "sourceCommit": sha, "architecture": "amd64"}
                  for i, (key, path) in enumerate(IMAGE_PATHS.items(), start=1)}
        with self.assertRaisesRegex(ValueError, "chart version"):
            build_application("v0.2.1", sha, images, template, "version: 0.2.0\n")
        with self.assertRaisesRegex(ValueError, "exactly the seven"):
            build_application("v0.2.1", sha, dict(list(images.items())[:-1]), template, "version: 0.2.1\n")

    def test_annotated_github_tag_resolves_to_commit_sha(self):
        class Response:
            headers = {}
            def __init__(self, body): self.body = body
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, *_): return self.body
        def opener(request, timeout):
            if "tags?" in request.full_url:
                return Response(b'[{"name":"v0.2.1","commit":{"sha":"b"},"type":"tag"}]')
            if "/git/ref/tags/v0.2.1" in request.full_url:
                return Response(b'{"object":{"sha":"b","type":"tag"}}')
            if "/git/tags/b" in request.full_url:
                return Response(b'{"object":{"sha":"' + b"a" * 40 + b'","type":"commit"}}')
            return Response(b"[]")
        self.assertEqual(resolve_tag_commit(fetch_tags(opener=opener)[0], opener=opener)["sha"], "a" * 40)

    def test_full_public_resolver_selects_trusted_latest_tag_and_index_digests(self):
        from scripts.ci_application import resolve_application
        class Response:
            def __init__(self, body, headers=None): self.body, self.headers = body, headers or {}
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, *_): return self.body
        sha = "a" * 40
        tag_object_sha = "b" * 40
        calls = []
        def opener(request, timeout):
            url = request.full_url
            calls.append(url)
            def response(body, digest=None):
                return Response(body, {"Docker-Content-Digest": digest} if digest else {})
            if "/tags?" in url:
                return response(json.dumps([{"name": "v0.2.1", "commit": {"sha": tag_object_sha}}]).encode())
            if "/git/ref/tags/v0.2.1" in url:
                return response(json.dumps({"object": {"sha": tag_object_sha, "type": "tag"}}).encode())
            if f"/git/tags/{tag_object_sha}" in url:
                return response((f'{{"object":{{"sha":"{sha}","type":"commit"}}}}').encode())
            if "/actions/workflows/release.yml/runs" in url:
                return response(json.dumps({"workflow_runs": [{"id": 9981, "run_number": 12, "event": "push",
                    "status": "completed", "conclusion": "success", "head_branch": "v0.2.1", "head_sha": sha}]}).encode())
            if "raw.githubusercontent.com" in url:
                return response(b"apiVersion: v2\nversion: 0.2.1\n")
            if "/token?" in url:
                return response(b'{"token":"anonymous"}')
            if "/manifests/v0.2.1" in url:
                config = json.dumps({"architecture": "amd64", "os": "linux", "config": {"Labels": {
                    "org.opencontainers.image.revision": sha, "org.opencontainers.image.version": "v0.2.1",
                    "org.opencontainers.image.source": "https://github.com/ANISHG-26/ottawa-fleet-app"}}}, separators=(",", ":")).encode()
                config_digest = "sha256:" + hashlib.sha256(config).hexdigest()
                child = json.dumps({"schemaVersion": 2, "config": {"digest": config_digest}, "layers": []}, separators=(",", ":")).encode()
                child_digest = "sha256:" + hashlib.sha256(child).hexdigest()
                arm_digest = "sha256:" + "f" * 64
                index = json.dumps({"schemaVersion": 2, "manifests": [
                    {"digest": child_digest, "platform": {"os": "linux", "architecture": "amd64"}},
                    {"digest": arm_digest, "platform": {"os": "linux", "architecture": "arm64"}},
                    {"digest": "sha256:" + "e" * 64, "platform": {"os": "unknown", "architecture": "unknown"},
                     "annotations": {"vnd.docker.reference.type": "attestation-manifest"}}]}, separators=(",", ":")).encode()
                return response(index, "sha256:" + hashlib.sha256(index).hexdigest())
            if "/manifests/sha256:" in url:
                config = json.dumps({"architecture": "amd64", "os": "linux", "config": {"Labels": {
                    "org.opencontainers.image.revision": sha, "org.opencontainers.image.version": "v0.2.1",
                    "org.opencontainers.image.source": "https://github.com/ANISHG-26/ottawa-fleet-app"}}}, separators=(",", ":")).encode()
                config_digest = "sha256:" + hashlib.sha256(config).hexdigest()
                child = json.dumps({"schemaVersion": 2, "config": {"digest": config_digest}, "layers": []}, separators=(",", ":")).encode()
                return response(child, "sha256:" + hashlib.sha256(child).hexdigest())
            if "/blobs/sha256:" in url:
                # Each config digest is content-addressed; all seven images may share this valid fixture.
                return response(json.dumps({"architecture": "amd64", "os": "linux", "config": {"Labels": {
                    "org.opencontainers.image.revision": sha, "org.opencontainers.image.version": "v0.2.1",
                    "org.opencontainers.image.source": "https://github.com/ANISHG-26/ottawa-fleet-app"}}}, separators=(",", ":")).encode())
            raise AssertionError(f"unexpected public read: {url}")
        result, receipt = resolve_application(Path(__file__).resolve().parents[1] / "gitops/environments/lab/application.json", opener=opener)
        self.assertEqual(receipt["tag"], "v0.2.1")
        self.assertEqual(receipt["sha"], sha)
        self.assertEqual(receipt["run_id"], 9981)
        self.assertEqual(result["spec"]["source"]["targetRevision"], sha)
        self.assertEqual(len([url for url in calls if "/token?" in url]), 7)

    def test_anonymous_registry_image_must_match_source_version_and_amd64(self):
        class Response:
            def __init__(self, body, digest=None): self.body, self.headers = body, {"Docker-Content-Digest": digest} if digest else {}
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def read(self, *_): return self.body
        sha = "a" * 40
        def make_opener(revision=sha, version="0.2.1", architecture="amd64", bad_digest=False):
            config_raw = json.dumps({"architecture": architecture, "os": "linux", "config": {"Labels": {
                "org.opencontainers.image.revision": revision, "org.opencontainers.image.version": "v" + version.removeprefix("v"),
                "org.opencontainers.image.source": "https://github.com/ANISHG-26/ottawa-fleet-app"}}}, separators=(",", ":")).encode()
            config_digest = "sha256:" + hashlib.sha256(config_raw).hexdigest()
            manifest_raw = json.dumps({"schemaVersion": 2, "config": {"digest": config_digest}, "layers": []}, separators=(",", ":")).encode()
            digest = "sha256:" + hashlib.sha256(manifest_raw).hexdigest()
            def opener(request, timeout):
                url = request.full_url
                if "/token?" in url: return Response(b'{"token":"anonymous-pull"}')
                if url.endswith("/manifests/v0.2.1"):
                    return Response(manifest_raw, "sha256:" + "0" * 64 if bad_digest else digest)
                return Response(config_raw)
            return opener
        self.assertRegex(inspect_image("web", "v0.2.1", sha, opener=make_opener())["reference"],
                         rf"^{GHCR}/web@sha256:[a-f0-9]{{64}}$")
        with self.assertRaisesRegex(ValueError, "source revision"):
            inspect_image("web", "v0.2.1", sha, opener=make_opener(revision="d" * 40))
        with self.assertRaisesRegex(ValueError, "immutable manifest digest"):
            inspect_image("web", "v0.2.1", sha, opener=make_opener(bad_digest=True))
        duplicate_index = json.dumps({"schemaVersion": 2, "manifests": [
            {"digest": "sha256:" + "1" * 64, "platform": {"os": "linux", "architecture": "amd64"}},
            {"digest": "sha256:" + "2" * 64, "platform": {"os": "linux", "architecture": "amd64"}}]}, separators=(",", ":")).encode()
        class IndexResponse(Response):
            pass
        def duplicate_amd64(request, timeout):
            if "/token?" in request.full_url:
                return IndexResponse(b'{"token":"anonymous-pull"}')
            return IndexResponse(duplicate_index, "sha256:" + hashlib.sha256(duplicate_index).hexdigest())
        with self.assertRaisesRegex(ValueError, "exactly one linux/amd64"):
            inspect_image("web", "v0.2.1", sha, opener=duplicate_amd64)

    def test_deploy_uses_exact_context_secret_stdin_and_readiness_contract(self):
        root = Path(__file__).resolve().parents[1]
        template = root / "gitops/environments/lab/application.json"
        release = {"tag": "v0.2.1", "sha": "a" * 40, "run_id": 123,
                   "digests": {name: "sha256:" + str(i) * 64 for i, name in enumerate(IMAGE_PATHS, 1)}}
        application = {"apiVersion": "argoproj.io/v1alpha1"}
        now = datetime.now(timezone.utc)
        app_status = {"status": {"sync": {"status": "Synced", "revision": release["sha"]},
                    "health": {"status": "Healthy"}, "operationState": {
                        "phase": "Succeeded", "syncResult": {"revision": release["sha"], "resources": [
                            {"kind": "Job", "name": "db-init-8-abc123", "hookPhase": "Succeeded"}]}}}}
        calls = []
        fleet_count = [20]
        def runner(command, **kwargs):
            calls.append((list(command), kwargs.get("input"), kwargs.get("env")))
            class Result:
                returncode = 0
                stderr = ""
                stdout = json.dumps({"cloudsql_private_ip": {"value": "10.0.0.3"},
                                     "cloudsql_database_name": {"value": "fleet"},
                                     "cloudsql_user_name": {"value": "fleet"}, "cloudsql_enabled": {"value": True},
                                     "cluster_name": {"value": "fleet-lab-r12345678"},
                                     "cluster_location": {"value": "northamerica-northeast1-a"},
                                     "cloudsql_instance_name": {"value": "fleet-lab-r12345678-postgres"}}) if command[:3] == ["terraform", "output", "-json"] else (
                    json.dumps(app_status) if "get" in command and "application" in command else (
                    json.dumps({"backgroundColor": "green"}) if "runtime-config.json" in " ".join(command) else (
                    json.dumps({"items": [{"vehicle_id": f"vehicle-{i:03d}"} for i in range(fleet_count[0])]}) if "limit=20" in " ".join(command) else (
                    json.dumps({"points": [{"latitude": 45.0, "longitude": -75.0} for _ in range(21)]}) if "routes/lansdowne-centretown-v1" in " ".join(command) else (
                    json.dumps({"status": "ok"}) if "readyz" in " ".join(command) else "")))))
            return Result()
        with patch("scripts.ci_application.resolve_application", return_value=(application, release)):
            result = deploy(project="project-one", zone="northamerica-northeast1-a", cluster="fleet-lab-r12345678",
                            kubeconfig="C:/private/kubeconfig", expires_at=(now + timedelta(minutes=20)).isoformat(),
                            secret_values={"database_password": "do-not-log-this-secret-0123456789", "cloudsql_enabled": True},
                            template_path=template, runner=runner, now=lambda: now)
        self.assertEqual(result, release)
        kubectl_calls = [call for call in calls if call[0][0] == "kubectl"]
        self.assertTrue(kubectl_calls)
        self.assertTrue(all(call[0][1] == "--context=gke_project-one_northamerica-northeast1-a_fleet-lab-r12345678" for call in kubectl_calls))
        inputs = [call[1] for call in kubectl_calls if call[1]]
        self.assertTrue(any("ottawa-fleet-database" in raw and "DATABASE_URL" in raw for raw in inputs))
        apply_calls = [call for call in kubectl_calls if "apply" in call[0]]
        self.assertEqual(len(apply_calls), 3)
        self.assertEqual(apply_calls[0][0][-1], "bootstrap/namespaces.yaml")
        self.assertIn("ottawa-fleet-database", apply_calls[1][1])
        self.assertIn("argoproj.io/v1alpha1", apply_calls[2][1])
        self.assertLess(kubectl_calls.index(apply_calls[1]), kubectl_calls.index(apply_calls[2]))
        self.assertTrue(all("do-not-log-this-secret" not in " ".join(call[0]) for call in calls))
        self.assertTrue(all(call[2] and call[2].get("KUBECONFIG") == "C:/private/kubeconfig" for call in kubectl_calls))
        self.assertEqual(sum("wait" in call[0] and "deployment/" in " ".join(call[0]) for call in kubectl_calls), 5)
        self.assertEqual(sum("--raw" in call[0] for call in kubectl_calls), 4)
        self.assertTrue(all("apply" not in call[0] for call in kubectl_calls if "--raw" in call[0]))

        app_status["status"]["operationState"]["phase"] = "Failed"
        before = len(calls)
        with patch("scripts.ci_application.resolve_application", return_value=(application, release)):
            with self.assertRaisesRegex(RuntimeError, "Argo application sync or migration hook failed"):
                deploy(project="project-one", zone="northamerica-northeast1-a", cluster="fleet-lab-r12345678",
                       kubeconfig="C:/private/kubeconfig", expires_at=(now + timedelta(minutes=20)).isoformat(),
                       secret_values={"database_password": "do-not-log-this-secret-0123456789", "cloudsql_enabled": True},
                       template_path=template, runner=runner, now=lambda: now)
        self.assertFalse(any("deployment/" in " ".join(call[0]) for call in calls[before:] if call[0][0] == "kubectl"))

        app_status["status"]["operationState"]["phase"] = "Succeeded"
        app_status["status"]["operationState"]["syncResult"]["resources"] = []
        clock = [now]
        before = len(calls)
        with patch("scripts.ci_application.resolve_application", return_value=(application, release)):
            with self.assertRaisesRegex(RuntimeError, "ten-minute CI wait bound"):
                deploy(project="project-one", zone="northamerica-northeast1-a", cluster="fleet-lab-r12345678",
                       kubeconfig="C:/private/kubeconfig", expires_at=(now + timedelta(minutes=20)).isoformat(),
                       secret_values={"database_password": "do-not-log-this-secret-0123456789", "cloudsql_enabled": True},
                       template_path=template, runner=runner,
                       sleep=lambda seconds: clock.__setitem__(0, clock[0] + timedelta(seconds=seconds)), now=lambda: clock[0])
        self.assertFalse(any("deployment/" in " ".join(call[0]) for call in calls[before:] if call[0][0] == "kubectl"))

        app_status["status"]["operationState"]["syncResult"]["resources"] = [
            {"kind": "Job", "name": "db-init-8-abc123", "hookPhase": "Succeeded"}]
        fleet_count[0] = 19
        with patch("scripts.ci_application.resolve_application", return_value=(application, release)):
            with self.assertRaisesRegex(RuntimeError, "20-vehicle synthetic profile"):
                deploy(project="project-one", zone="northamerica-northeast1-a", cluster="fleet-lab-r12345678",
                       kubeconfig="C:/private/kubeconfig", expires_at=(now + timedelta(minutes=20)).isoformat(),
                       secret_values={"database_password": "do-not-log-this-secret-0123456789", "cloudsql_enabled": True},
                       template_path=template, runner=runner, now=lambda: now)

    def test_expired_run_does_not_apply_any_application_manifest(self):
        root = Path(__file__).resolve().parents[1]
        calls = []
        def runner(command, **kwargs):
            calls.append(command)
            raise AssertionError("expired run must not invoke kubectl")
        now = datetime.now(timezone.utc)
        with patch("scripts.ci_application.resolve_application", return_value=({}, {})):
            with self.assertRaisesRegex(RuntimeError, "expiry elapsed"):
                deploy(project="project-one", zone="northamerica-northeast1-a", cluster="fleet-lab-r12345678",
                       kubeconfig="C:/private/kubeconfig", expires_at=(now - timedelta(seconds=1)).isoformat(),
                       secret_values={}, template_path=root / "gitops/environments/lab/application.json",
                       runner=runner, now=lambda: now)
        self.assertEqual(calls, [])

    def test_database_outputs_must_belong_to_exact_run_before_secret_apply(self):
        root = Path(__file__).resolve().parents[1]
        now = datetime.now(timezone.utc)
        release = {"tag": "v0.2.1", "sha": "a" * 40, "run_id": 123,
                   "digests": {name: "sha256:" + str(i) * 64 for i, name in enumerate(IMAGE_PATHS, 1)}}
        calls = []
        outputs = {key: {"value": value} for key, value in {
            "cloudsql_enabled": True, "cluster_name": "a-different-run", "cluster_location": "northamerica-northeast1-a",
            "cloudsql_instance_name": "a-different-run-postgres", "cloudsql_private_ip": "10.0.0.3",
            "cloudsql_database_name": "fleet", "cloudsql_user_name": "fleet"}.items()}
        def runner(command, **kwargs):
            calls.append(list(command))
            class Result:
                returncode = 0
                stderr = ""
                stdout = json.dumps(outputs)
            return Result()
        with patch("scripts.ci_application.resolve_application", return_value=({}, release)):
            with self.assertRaisesRegex(ValueError, "exact lab run"):
                deploy(project="project-one", zone="northamerica-northeast1-a", cluster="fleet-lab-r12345678",
                       kubeconfig="C:/private/kubeconfig", expires_at=(now + timedelta(minutes=20)).isoformat(),
                       secret_values={"database_password": "private-secret-value-with-32-characters", "cloudsql_enabled": True},
                       template_path=root / "gitops/environments/lab/application.json", runner=runner, now=lambda: now)
        self.assertFalse(any(command[0] == "kubectl" for command in calls))

    def test_secret_apply_failure_does_not_expose_manifest_or_diagnostic_text(self):
        root = Path(__file__).resolve().parents[1]
        now = datetime.now(timezone.utc)
        password = "very-private-database-password-012345"
        release = {"tag": "v0.2.1", "sha": "a" * 40, "run_id": 123, "digests": {}}
        outputs = {key: {"value": value} for key, value in {
            "cloudsql_enabled": True, "cluster_name": "fleet-lab-r12345678",
            "cluster_location": "northamerica-northeast1-a", "cloudsql_instance_name": "fleet-lab-r12345678-postgres",
            "cloudsql_private_ip": "10.0.0.3", "cloudsql_database_name": "fleet", "cloudsql_user_name": "fleet"}.items()}
        def runner(command, **kwargs):
            class Result:
                returncode = 1 if command[0] == "kubectl" and command[-2:] == ["-f", "-"] else 0
                stdout = json.dumps(outputs) if command[0] == "terraform" else password
                stderr = password
            return Result()
        with patch("scripts.ci_application.resolve_application", return_value=({}, release)):
            with self.assertRaises(RuntimeError) as caught:
                deploy(project="project-one", zone="northamerica-northeast1-a", cluster="fleet-lab-r12345678",
                       kubeconfig="C:/private/kubeconfig", expires_at=(now + timedelta(minutes=20)).isoformat(),
                       secret_values={"database_password": password, "cloudsql_enabled": True},
                       template_path=root / "gitops/environments/lab/application.json", runner=runner, now=lambda: now)
        self.assertNotIn(password, str(caught.exception))
        def timed_out(*_args, **_kwargs):
            raise subprocess.TimeoutExpired("kubectl", 1, output=password, stderr=password)
        with self.assertRaises(RuntimeError) as timeout_error:
            _run(["kubectl"], runner=timed_out)
        self.assertNotIn(password, str(timeout_error.exception))

if __name__ == "__main__": unittest.main()
