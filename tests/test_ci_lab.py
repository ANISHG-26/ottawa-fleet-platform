"""Behavior checks for bounded CI provisioning and expiry registration."""
from datetime import datetime, timedelta, timezone
import json
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ci_lab


def reviewed_tfvars():
    return json.dumps({
        "project_id": "private-project-123", "zone": "us-central1-a",
        "node_service_account_id": "fleet-lab-nodes", "machine_type": "e2-standard-2",
        "node_count": 1, "node_disk_size_gb": 30, "resource_plan_reviewed": True,
        "review_project_id": "private-project-123", "review_zone": "us-central1-a",
        "inventory_reference": "private:inventory", "quota_reviewed": True,
        "pricing_reviewed": True, "workload_sizing_reference": "private:sizing",
        "workload_sizing_reviewed": True, "teardown_owner_reference": "private:owner",
        "inventory_matches_review": True, "reviewed_resource_ceiling": 1,
        "ceiling_matches_review": True, "project_zone_match_reviewed": True,
        "cloudsql_enabled": True, "cloudsql_plan_reviewed": True,
        "cloudsql_quota_reviewed": True, "cloudsql_pricing_reviewed": True,
        "cloudsql_inventory_reference": "private:sql-inventory",
        "database_password": "a" * 48,
        "retained_network_name": "fleet-lab-ci-network",
    })


def environment():
    return {
        "GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "37131621545",
        "GITHUB_API_URL": "https://api.github.com", "GITHUB_REPOSITORY": "ANISHG-26/ottawa-fleet-platform",
        "GCP_PROJECT_ID": "private-project-123", "GCP_WIF_PROVIDER": "private/provider",
        "GCP_DEPLOY_SERVICE_ACCOUNT": "deploy@private-project-123.iam.gserviceaccount.com",
        "LAB_STATE_BUCKET": "private-state-bucket", "LAB_TFVARS_JSON": reviewed_tfvars(),
        "LAB_TASK_LOCATION": "us-central1", "LAB_TASK_QUEUE": "fleet-cleanup",
        "LAB_SHUTDOWN_URL": "https://cleanup.example.run", "LAB_TASK_INVOKER_SERVICE_ACCOUNT": "task@private-project-123.iam.gserviceaccount.com",
    }


class CiLabContractTests(unittest.TestCase):
    def test_only_manual_exact_main_revision_is_accepted(self):
        ci_lab.validate_dispatch("workflow_dispatch", "refs/heads/main", "a" * 40, "a" * 40)
        for values in (
            ("pull_request", "refs/heads/main", "a" * 40, "a" * 40),
            ("workflow_dispatch", "refs/heads/feature", "a" * 40, "a" * 40),
            ("workflow_dispatch", "refs/heads/main", "a" * 40, "b" * 40),
            ("workflow_dispatch", "refs/heads/main", "main", "a" * 40),
        ):
            with self.subTest(values=values), self.assertRaises(ValueError):
                ci_lab.validate_dispatch(*values)

    def test_project_mismatch_fails_before_cloud_mutations(self):
        source_root = Path(__file__).resolve().parents[1]
        head = __import__("subprocess").run(["git", "rev-parse", "HEAD"], cwd=source_root,
                                            capture_output=True, text=True, check=True).stdout.strip()
        env = environment()
        env["GITHUB_SHA"] = head
        env["GCP_PROJECT_ID"] = "other-private-project"
        with self.assertRaisesRegex(ValueError, "must match the private reviewed"):
            ci_lab.run_pipeline(env, source_root=source_root)

    def test_expiry_is_exactly_two_hours_from_actions_start(self):
        start = "2026-10-03T12:00:00Z"
        started, expires = ci_lab.expiry_from_run_start(start)
        self.assertEqual(started, start)
        self.assertEqual(expires, "2026-10-03T14:00:00Z")
        with self.assertRaises(ValueError):
            ci_lab.expiry_from_run_start("2026-10-03T12:00:00-04:00")

    def test_active_lease_rejects_another_run_and_resumes_only_exact_identity(self):
        request = {
            "run_id": "37131621545", "source_revision": "a" * 40,
            "cluster_name": "fleet-lab-r37131621545", "state_prefix": "gcp-lab/runs/37131621545",
            "started_at": "2026-10-03T12:00:00Z", "expires_at": "2026-10-03T14:00:00Z",
        }
        class Response:
            def __init__(self, data): self.data = data
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return self.data

        calls = []
        def opener(request_obj, timeout):
            calls.append(request_obj)
            if request_obj.get_method() == "POST":
                from urllib.error import HTTPError
                raise HTTPError(request_obj.full_url, 412, "exists", {}, None)
            if "alt=media" in request_obj.full_url:
                return Response(json.dumps(request).encode())
            return Response(json.dumps({"generation": "938475"}).encode())

        generation, resumed = ci_lab.acquire_active_lease(
            bucket="private-state-bucket", request=request, token="token", opener=opener,
        )
        self.assertEqual((generation, resumed), ("938475", True))
        self.assertTrue(any("ifGenerationMatch=0" in call.full_url for call in calls))

        other = dict(request, run_id="37131621546", cluster_name="fleet-lab-r37131621546",
                     state_prefix="gcp-lab/runs/37131621546")
        with self.assertRaisesRegex(RuntimeError, "another CI lab run"):
            ci_lab.acquire_active_lease(bucket="private-state-bucket", request=other,
                                        token="token", opener=opener)

    def test_cleanup_source_archive_is_compressed_and_allowlisted(self):
        import io
        import tarfile
        archive_io = io.BytesIO()
        with tarfile.open(fileobj=archive_io, mode="w:gz") as archive:
            payload = b"resource {}"
            info = tarfile.TarInfo("terraform/lab/main.tf")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))

        class Result:
            stdout = archive_io.getvalue()

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "source.tgz"
            with patch("scripts.lab_cleanup.subprocess.run", return_value=Result()) as run:
                result = ci_lab.create_source_archive(
                    source_revision="a" * 40, output_path=target,
                    repo_root=Path(__file__).resolve().parents[1],
                    paths=("terraform/lab", "scripts/lab_cleanup.py", "scripts/private_diagnostics.py"),
                )
            self.assertEqual(result, target.resolve())
            with tarfile.open(result, mode="r:gz") as source:
                self.assertEqual(source.getnames(), ["terraform/lab/main.tf"])
            self.assertIn("--format=tar.gz", run.call_args.args[0])
            self.assertIn("scripts/private_diagnostics.py", run.call_args.args[0])
            with self.assertRaises(ValueError):
                ci_lab.create_source_archive(source_revision="a" * 40, output_path=target,
                                             repo_root=Path(__file__).resolve().parents[1],
                                             paths=(".",))

    def test_registered_task_is_exact_run_only_oidc_task_at_expiry(self):
        class Response:
            def __init__(self, data): self.data = data
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return self.data

        captured = {}
        def opener(request, timeout):
            captured["url"] = request.full_url
            captured["body"] = json.loads(request.data)["task"]
            captured["response_view"] = json.loads(request.data)["responseView"]
            captured["headers"] = request.headers
            return Response(json.dumps({"name": captured["body"]["name"],
                                        "scheduleTime": captured["body"]["scheduleTime"],
                                        "httpRequest": captured["body"]["httpRequest"]}).encode())

        ci_lab._create_task(
            project="p", location="l", queue="q", task_id="fleet-r37131621545",
            url="https://cleanup.example.run", audience="https://cleanup.example.run",
            invoker="task@p.iam.gserviceaccount.com", schedule_time="2026-10-03T14:00:00Z",
            run_id="37131621545", token="short-lived-token", opener=opener,
        )
        task = captured["body"]
        self.assertEqual(captured["response_view"], "FULL")
        self.assertEqual(task["scheduleTime"], "2026-10-03T14:00:00Z")
        self.assertEqual(base64.b64decode(task["httpRequest"]["body"]), b'{"run_id":"37131621545"}')
        self.assertEqual(task["httpRequest"]["oidcToken"], {
            "serviceAccountEmail": "task@p.iam.gserviceaccount.com",
            "audience": "https://cleanup.example.run",
        })
        self.assertIn("Bearer short-lived-token", captured["headers"].get("Authorization", ""))

        request_urls = []
        def duplicate_opener(request, timeout):
            request_urls.append(request.full_url)
            if request.get_method() == "POST":
                from urllib.error import HTTPError
                raise HTTPError(request.full_url, 409, "exists", {}, None)
            return Response(json.dumps({"name": task["name"], "scheduleTime": task["scheduleTime"],
                                        "httpRequest": task["httpRequest"]}).encode())
        ci_lab._create_task(
            project="p", location="l", queue="q", task_id="fleet-r37131621545",
            url="https://cleanup.example.run", audience="https://cleanup.example.run",
            invoker="task@p.iam.gserviceaccount.com", schedule_time="2026-10-03T14:00:00Z",
            run_id="37131621545", token="short-lived-token", opener=duplicate_opener,
        )
        self.assertTrue(request_urls[1].endswith("?responseView=FULL"))

    def test_inputs_upload_and_task_registration_precede_apply(self):
        events = []
        source_root = Path(__file__).resolve().parents[1]
        head = __import__("subprocess").run(["git", "rev-parse", "HEAD"], cwd=source_root,
                                            capture_output=True, text=True, check=True).stdout.strip()
        env = environment()
        env["GITHUB_SHA"] = head
        run_start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()

        def fake_runner(command, **kwargs):
            events.append(("command", list(command)))
            class Result:
                returncode = 0
                stdout = "fake-token" if command[:3] == ["gcloud", "auth", "print-access-token"] else ""
                stderr = ""
            return Result()

        def archive(*, output_path, **kwargs):
            Path(output_path).write_bytes(b"private cleanup source")
            return Path(output_path)

        original_write = ci_lab.write_run_inputs
        private_paths = []
        def write_inputs(**kwargs):
            result = original_write(**kwargs)
            private_paths.extend(Path(result[key]).resolve() for key in ("tfvars", "backend", "request_file"))
            return result

        def upload(path, uri, runner):
            events.append(("upload", uri, Path(path).resolve()))
            private_paths.append(Path(path).resolve())

        def register(**kwargs):
            events.append(("task", kwargs["schedule_time"], kwargs["task_id"]))

        now = datetime.fromisoformat(run_start)
        with patch.object(ci_lab, "fetch_run_started_at", return_value=run_start), \
             patch.object(ci_lab, "create_source_archive", side_effect=archive), \
             patch.object(ci_lab, "write_run_inputs", side_effect=write_inputs), \
             patch.object(ci_lab, "_upload", side_effect=upload), \
             patch.object(ci_lab, "acquire_active_lease", return_value=("12345", False)), \
             patch.object(ci_lab, "_create_task", side_effect=register), \
             patch.object(ci_lab, "datetime") as dt:
            dt.now.return_value = now + timedelta(minutes=2)
            dt.fromisoformat = datetime.fromisoformat
            result = ci_lab.run_pipeline(env, runner=fake_runner, source_root=source_root)

        upload_events = [event for event in events if event[0] == "upload"]
        task_index = next(i for i, event in enumerate(events) if event[0] == "task")
        apply_index = next(i for i, event in enumerate(events) if event[0] == "command" and event[1][0:2] == ["terraform", "apply"])
        self.assertEqual(len(upload_events), 4)
        self.assertLess(max(i for i, e in enumerate(events) if e[0] == "upload"), task_index)
        self.assertLess(task_index, apply_index)
        self.assertIn("gs://private-state-bucket/gcp-lab/runs/37131621545/source.tgz", [event[1] for event in upload_events])
        self.assertTrue(all(not path.is_relative_to(source_root) for path in private_paths))
        self.assertEqual(result["task"], "fleet-r37131621545")

    def test_apply_failure_runs_same_registered_expiry_task_immediately(self):
        source_root = Path(__file__).resolve().parents[1]
        head = __import__("subprocess").run(["git", "rev-parse", "HEAD"], cwd=source_root,
                                            capture_output=True, text=True, check=True).stdout.strip()
        env = environment()
        env["GITHUB_SHA"] = head
        run_start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        commands = []
        with patch.object(ci_lab, "fetch_run_started_at", return_value=run_start), \
             patch.object(ci_lab, "create_source_archive", side_effect=lambda *, output_path, **kw: (Path(output_path).write_bytes(b"archive") or Path(output_path))), \
             patch.object(ci_lab, "_upload"), patch.object(ci_lab, "acquire_active_lease", return_value=("12345", False)), \
             patch.object(ci_lab, "_create_task") as register, \
             patch.object(ci_lab, "datetime") as dt, \
             patch.object(ci_lab.tempfile, "mkdtemp", return_value=tempfile.mkdtemp()):
            dt.now.return_value = datetime.fromisoformat(run_start) + timedelta(minutes=1)
            dt.fromisoformat = datetime.fromisoformat
            def runner(command, **kwargs):
                commands.append(list(command))
                class Result:
                    returncode = 1 if command[:2] == ["terraform", "apply"] else 0
                    stdout = "token" if command[:3] == ["gcloud", "auth", "print-access-token"] else ""
                    stderr = ""
                return Result()
            with self.assertRaisesRegex(RuntimeError, "terraform, exit 1"):
                ci_lab.run_pipeline(env, runner=runner, source_root=source_root)
        register.assert_called_once()
        self.assertTrue(any(command[:3] == ["gcloud", "tasks", "run"] and "fleet-r37131621545" in command for command in commands))

    def test_expiry_registration_failure_aborts_before_terraform(self):
        source_root = Path(__file__).resolve().parents[1]
        head = __import__("subprocess").run(["git", "rev-parse", "HEAD"], cwd=source_root,
                                            capture_output=True, text=True, check=True).stdout.strip()
        env = environment()
        env["GITHUB_SHA"] = head
        run_start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        commands = []
        with patch.object(ci_lab, "fetch_run_started_at", return_value=run_start), \
             patch.object(ci_lab, "create_source_archive", side_effect=lambda *, output_path, **kw: (Path(output_path).write_bytes(b"archive") or Path(output_path))), \
             patch.object(ci_lab, "_upload"), patch.object(ci_lab, "acquire_active_lease", return_value=("12345", False)), \
             patch.object(ci_lab, "_create_task", side_effect=RuntimeError("task rejected")), \
             patch.object(ci_lab, "release_active_lease") as release, \
             patch.object(ci_lab, "datetime") as dt:
            dt.now.return_value = datetime.fromisoformat(run_start) + timedelta(minutes=1)
            dt.fromisoformat = datetime.fromisoformat
            def runner(command, **kwargs):
                commands.append(list(command))
                class Result:
                    returncode = 0
                    stdout = "token" if command[:3] == ["gcloud", "auth", "print-access-token"] else ""
                    stderr = ""
                return Result()
            with self.assertRaisesRegex(RuntimeError, "task rejected"):
                ci_lab.run_pipeline(env, runner=runner, source_root=source_root)
        release.assert_called_once()
        self.assertFalse(any(command[:1] == ["terraform"] for command in commands))


if __name__ == "__main__":
    unittest.main()
