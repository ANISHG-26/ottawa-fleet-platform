"""Focused tests for the authenticated shutdown dispatcher state machine."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import base64
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "functions" / "lab_shutdown"))
sys.path.insert(0, str(ROOT))
from functions.lab_shutdown import main as shutdown  # noqa: E402


RUN_ID = "12345678901"
PREFIX = f"gcp-lab/runs/{RUN_ID}"
REQUEST = {"run_id": RUN_ID, "source_revision": "a" * 40,
           "cluster_name": f"fleet-lab-r{RUN_ID}", "state_prefix": PREFIX,
           "started_at": "2026-10-03T12:00:00Z", "expires_at": "2026-10-03T14:00:00Z"}


class FakeBackend:
    project = "fleet-lab-project"
    bucket = "private-cleanup-bucket"
    retained_network_name = "fleet-lab-ci-shared"

    def __init__(self, builds=None):
        self.objects = {
            f"{PREFIX}/request.json": json.dumps(REQUEST).encode(),
            f"{PREFIX}/source.tgz": b"immutable-source",
            f"{PREFIX}/terraform.tfvars.json": json.dumps({
                "project_id": self.project, "cluster_name": REQUEST["cluster_name"],
                "retained_network_name": self.retained_network_name}).encode(),
            f"{PREFIX}/backend.hcl": f'bucket = "{self.bucket}"\nprefix = "{PREFIX}"\n'.encode(),
        }
        self.generation = 0
        self.builds = list(builds or [])
        self.direct_builds = {}
        self.created = []
        self.tasks = []
        self.released = []
        self.fail_task = False

    def read_object(self, name):
        if name not in self.objects:
            return None
        return self.objects[name], str(self.generation)

    def write_object_cas(self, name, value, generation):
        current = self.objects.get(name)
        if (current is None and generation is not None) or (current is not None and generation != str(self.generation)):
            return None
        self.generation += 1
        self.objects[name] = json.dumps(value).encode()
        return str(self.generation)

    def list_builds(self, tag):
        assert tag == f"lab-cleanup-{RUN_ID}"
        return self.builds

    def get_build(self, name):
        return next((build for build in self.builds if build.get("name") == name), self.direct_builds.get(name, {}))

    def create_build(self, tag, run_id, source_generation, request_uri, tfvars_uri, backend_uri):
        build = {"name": f"build-{len(self.created)+1}", "status": "QUEUED"}
        self.created.append((tag, run_id, source_generation, request_uri, tfvars_uri, backend_uri))
        self.builds.append(build)
        return build

    def create_poll_task(self, run_id, attempt, delay=90):
        if self.fail_task:
            raise RuntimeError("Cloud Tasks unavailable")
        self.tasks.append((run_id, attempt, delay))

    def release_active_lease(self, run_id):
        self.released.append(run_id)
        return True


class ShutdownTests(unittest.TestCase):
    def test_rejects_invalid_and_manual_cluster_requests_without_cloud_actions(self):
        backend = FakeBackend()
        _, status = shutdown.dispatch("abc", backend)
        self.assertEqual(status, 400)
        self.assertEqual(backend.created, [])
        backend = FakeBackend()
        manual = dict(REQUEST, cluster_name=f"fleet-lab-r{RUN_ID}-manual")
        backend.objects[f"{PREFIX}/request.json"] = json.dumps(manual).encode()
        _, status = shutdown.dispatch(RUN_ID, backend)
        self.assertEqual(status, 400)
        self.assertEqual(backend.created, [])
        backend = FakeBackend()
        request = dict(REQUEST, unexpected="manual")
        backend.objects[f"{PREFIX}/request.json"] = json.dumps(request).encode()
        _, status = shutdown.dispatch(RUN_ID, backend)
        self.assertEqual(status, 400)
        self.assertEqual(backend.created, [])

    def test_rejects_run_inputs_for_a_different_retained_network(self):
        backend = FakeBackend()
        variables = json.loads(backend.objects[f"{PREFIX}/terraform.tfvars.json"])
        variables["retained_network_name"] = "some-manual-network"
        backend.objects[f"{PREFIX}/terraform.tfvars.json"] = json.dumps(variables).encode()
        _, status = shutdown.dispatch(RUN_ID, backend)
        self.assertEqual(status, 400)
        self.assertEqual(backend.created, [])

    def test_early_pipeline_failure_can_dispatch_before_two_hour_expiry(self):
        backend = FakeBackend()
        body, status = shutdown.dispatch(RUN_ID, backend, now=datetime(2026, 10, 3, 12, 5, tzinfo=timezone.utc))
        self.assertEqual(status, 202)
        self.assertEqual(body["state"], "running")
        self.assertEqual(len(backend.created), 1)

    def test_reuses_existing_active_build_instead_of_creating_another(self):
        backend = FakeBackend([{"name": "existing-build", "status": "WORKING"}])
        body, status = shutdown.dispatch(RUN_ID, backend)
        self.assertEqual((status, body["build"]), (202, "existing-build"))
        self.assertEqual(backend.created, [])
        self.assertEqual(len(backend.tasks), 1)

    def test_three_failed_builds_stop_with_retryable_server_error(self):
        backend = FakeBackend([{"name": f"failed-{n}", "status": "FAILURE"} for n in range(3)])
        body, status = shutdown.dispatch(RUN_ID, backend)
        self.assertEqual(status, 500)
        self.assertIn("retry limit", body["error"])
        self.assertEqual(backend.created, [])

    def test_poll_registration_failure_returns_http_500_and_keeps_marker(self):
        backend = FakeBackend()
        backend.fail_task = True
        with patch.object(shutdown, "GoogleBackend", return_value=backend), patch.object(shutdown, "_env", return_value={}):
            response, status = shutdown.main(_Request({"run_id": RUN_ID}))
        self.assertEqual(status, 500)
        marker = json.loads(backend.objects[f"{PREFIX}/shutdown.json"])
        self.assertEqual(marker["state"], "running")
        self.assertEqual(len(backend.created), 1)

    def test_successful_build_reconciles_marker_and_releases_own_lease(self):
        backend = FakeBackend([{"name": "ok-build", "status": "SUCCESS"}])
        body, status = shutdown.dispatch(RUN_ID, backend)
        self.assertEqual((status, body["state"]), (200, "complete"))
        self.assertEqual(backend.released, [RUN_ID])

    def test_empty_tag_listing_uses_exact_build_get_and_reconciles_success(self):
        backend = FakeBackend()
        build_name = "projects/fleet-lab-project/locations/northamerica-northeast1/builds/abc123"
        backend.objects[f"{PREFIX}/shutdown.json"] = json.dumps({
            "run_id": RUN_ID, "attempt": 1, "state": "running", "build_name": build_name,
            "launched_at": "2026-10-03T12:00:00+00:00"}).encode()
        backend.direct_builds[build_name] = {"name": build_name, "status": "SUCCESS",
                                              "tags": [f"lab-cleanup-{RUN_ID}"]}
        body, status = shutdown.dispatch(RUN_ID, backend)
        self.assertEqual((status, body["state"]), (200, "complete"))
        self.assertEqual(backend.released, [RUN_ID])

    def test_cloud_build_operation_metadata_is_normalized_to_canonical_build(self):
        tag = f"lab-cleanup-{RUN_ID}"
        build = {"name": "projects/123456789012/locations/northamerica-northeast1/builds/b123",
                 "id": "b123", "projectId": "fleet-lab-project",
                 "status": "QUEUED", "tags": [tag]}

        class Response:
            status_code = 200
            content = b"{operation}"
            def __init__(self, payload): self.payload = payload
            def raise_for_status(self): pass
            def json(self): return self.payload

        class Session:
            def __init__(self, payload): self.payload = payload; self.params = None
            def post(self, url, **kwargs):
                self.params = kwargs.get("params")
                return Response(self.payload)

        env = {"PROJECT_ID": "fleet-lab-project", "STATE_BUCKET": "private-cleanup-bucket",
               "PROJECT_NUMBER": "123456789012",
               "EXPECTED_RETAINED_NETWORK": "fleet-lab-ci-shared",
               "CLOUD_BUILD_LOCATION": "northamerica-northeast1", "TASK_QUEUE": "cleanup",
               "FUNCTION_URL": "https://cleanup.example", "CLEANUP_SERVICE_ACCOUNT": "cleanup@example"}
        session = Session({"name": "operations/build-create-1", "metadata": {"build": build}})
        backend = shutdown.GoogleBackend(env, session)
        actual = backend.create_build(tag, RUN_ID, "7", "gs://b/r/request.json",
                                      "gs://b/r/tfvars.json", "gs://b/r/backend.hcl")
        self.assertEqual(actual["name"], "projects/fleet-lab-project/locations/northamerica-northeast1/builds/b123")
        self.assertEqual(actual["id"], "b123")
        self.assertEqual(session.params, {"projectId": "fleet-lab-project"})
        unconfigured_number = dict(env)
        del unconfigured_number["PROJECT_NUMBER"]
        backend = shutdown.GoogleBackend(unconfigured_number,
            Session({"name": "operations/build-create-1", "metadata": {"build": build}}))
        with self.assertRaisesRegex(RuntimeError, "outside the configured project and location"):
            backend.create_build(tag, RUN_ID, "7", "gs://b/r/request.json",
                                 "gs://b/r/tfvars.json", "gs://b/r/backend.hcl")

    def test_cloud_build_done_response_is_accepted_and_wrong_location_rejected(self):
        tag = f"lab-cleanup-{RUN_ID}"
        build = {"name": "projects/fleet-lab-project/locations/northamerica-northeast1/builds/b124",
                 "id": "b124", "projectId": "fleet-lab-project",
                 "status": "SUCCESS", "tags": [tag]}

        class Response:
            status_code = 200
            content = b"{}"
            def __init__(self, payload): self.payload = payload
            def raise_for_status(self): pass
            def json(self): return self.payload
        class Session:
            def __init__(self, payload): self.payload = payload
            def post(self, url, **kwargs): return Response(self.payload)
        env = {"PROJECT_ID": "fleet-lab-project", "STATE_BUCKET": "private-cleanup-bucket",
               "EXPECTED_RETAINED_NETWORK": "fleet-lab-ci-shared",
               "CLOUD_BUILD_LOCATION": "northamerica-northeast1", "TASK_QUEUE": "cleanup",
               "FUNCTION_URL": "https://cleanup.example", "CLEANUP_SERVICE_ACCOUNT": "cleanup@example"}
        backend = shutdown.GoogleBackend(env, Session({"done": True, "response": build}))
        self.assertEqual(backend.create_build(tag, RUN_ID, "7", "gs://b/r/request.json",
                                              "gs://b/r/tfvars.json", "gs://b/r/backend.hcl"), build)
        wrong = dict(build, name="projects/other-project/locations/northamerica-northeast1/builds/b124")
        backend.http = Session({"metadata": {"build": wrong}})
        with self.assertRaisesRegex(RuntimeError, "outside the configured project and location"):
            backend.create_build(tag, RUN_ID, "7", "gs://b/r/request.json",
                                 "gs://b/r/tfvars.json", "gs://b/r/backend.hcl")

    def test_cloud_build_operation_error_or_missing_build_is_rejected(self):
        tag = f"lab-cleanup-{RUN_ID}"
        class Response:
            status_code = 200
            content = b"{}"
            def __init__(self, payload): self.payload = payload
            def raise_for_status(self): pass
            def json(self): return self.payload
        class Session:
            def __init__(self, payload): self.payload = payload
            def post(self, url, **kwargs): return Response(self.payload)
        env = {"PROJECT_ID": "fleet-lab-project", "STATE_BUCKET": "private-cleanup-bucket",
               "EXPECTED_RETAINED_NETWORK": "fleet-lab-ci-shared",
               "CLOUD_BUILD_LOCATION": "northamerica-northeast1", "TASK_QUEUE": "cleanup",
               "FUNCTION_URL": "https://cleanup.example", "CLEANUP_SERVICE_ACCOUNT": "cleanup@example"}
        for payload, message in (({"error": {"code": 3}}, "rejected"),
                                 ({"name": "operations/create-1", "metadata": {}}, "did not include its build resource")):
            backend = shutdown.GoogleBackend(env, Session(payload))
            with self.subTest(payload=payload), self.assertRaisesRegex(RuntimeError, message):
                backend.create_build(tag, RUN_ID, "7", "gs://b/r/request.json",
                                     "gs://b/r/tfvars.json", "gs://b/r/backend.hcl")

    def test_gcs_object_paths_are_escaped_for_slash_containing_names(self):
        class Response:
            status_code = 200
            content = b"{}"
            def raise_for_status(self): pass
            def json(self): return {"generation": "42"}

        class Session:
            def __init__(self): self.urls = []
            def get(self, url, **kwargs):
                self.urls.append(url)
                return Response()

        session = Session()
        backend = shutdown.GoogleBackend({"PROJECT_ID": "fleet-lab-project", "STATE_BUCKET": "private-cleanup-bucket",
            "EXPECTED_RETAINED_NETWORK": "fleet-lab-ci-shared",
            "CLOUD_BUILD_LOCATION": "northamerica-northeast1", "TASK_QUEUE": "cleanup",
            "FUNCTION_URL": "https://cleanup.example", "CLEANUP_SERVICE_ACCOUNT": "cleanup@example"}, session)
        backend.read_object("gcp-lab/runs/12345678901/request.json")
        self.assertIn("gcp-lab%2Fruns%2F12345678901%2Frequest.json", session.urls[0])

    def test_cloud_tasks_body_uses_rest_base64_json_encoding(self):
        class Response:
            status_code = 200
            def raise_for_status(self): pass
        class Session:
            def __init__(self): self.body = None
            def post(self, url, **kwargs):
                self.body = kwargs["json"]
                return Response()
        session = Session()
        backend = shutdown.GoogleBackend({"PROJECT_ID": "fleet-lab-project", "STATE_BUCKET": "private-cleanup-bucket",
            "EXPECTED_RETAINED_NETWORK": "fleet-lab-ci-shared",
            "CLOUD_BUILD_LOCATION": "northamerica-northeast1", "TASK_QUEUE": "cleanup",
            "TASKS_LOCATION": "northamerica-northeast1", "TASK_INVOKER_SERVICE_ACCOUNT": "invoke@example",
            "FUNCTION_URL": "https://cleanup.example", "CLEANUP_SERVICE_ACCOUNT": "cleanup@example"}, session)
        backend.create_poll_task(RUN_ID, 1)
        encoded = session.body["task"]["httpRequest"]["body"]
        self.assertEqual(json.loads(base64.b64decode(encoded)), {"run_id": RUN_ID})


class _Request:
    def __init__(self, body):
        self.body = body

    def get_json(self, silent=True):
        return self.body


if __name__ == "__main__":
    unittest.main()
