"""Behavior checks for the disposable GCP lab deployment contract."""
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.lab_cleanup import (
    MAX_LAB_SECONDS,
    write_run_inputs,
    validate_cleanup_request,
)
from scripts.gcp_lab import (
    ARGO_MANIFEST_SHA256, bootstrap_commands, expected_context,
    resolve_executable, validate_target,
)


class LabCleanupContractTests(unittest.TestCase):
    def test_windows_command_shims_resolve_to_absolute_cmd_wrapper(self):
        environment = {"PATH": r"C:\GoogleCloudSDK\bin", "COMSPEC": r"C:\Windows\System32\cmd.exe"}
        with patch("scripts.gcp_lab.shutil.which", return_value=r"C:\GoogleCloudSDK\bin\gcloud.cmd") as which:
            resolved = resolve_executable(["gcloud", "container", "clusters", "list"], environment, windows=True)
        which.assert_called_once_with("gcloud", path=environment["PATH"])
        self.assertEqual(resolved[:4], [environment["COMSPEC"], "/d", "/s", "/c"])
        self.assertTrue(resolved[4].startswith(r"C:\GoogleCloudSDK\bin\gcloud.cmd"))
        self.assertIn("clusters list", resolved[4])

    def test_expiry_is_bound_to_one_immutable_run_and_exactly_two_hours(self):
        started = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
        valid = {
            "run_id": "37131621545",
            "source_revision": "a" * 40,
            "cluster_name": "fleet-lab-r37131621545",
            "state_prefix": "gcp-lab/runs/37131621545",
            "started_at": started.isoformat(),
            "expires_at": (started + timedelta(seconds=MAX_LAB_SECONDS)).isoformat(),
        }
        self.assertEqual(validate_cleanup_request(valid), valid)

        for mutate in (
            lambda p: p.update(cluster_name="fleet-lab"),
            lambda p: p.update(state_prefix="gcp-lab/shared"),
            lambda p: p.update(source_revision="HEAD"),
            lambda p: p.update(expires_at=(started + timedelta(hours=3)).isoformat()),
            lambda p: p.update(run_id="../../other"),
        ):
            invalid = dict(valid)
            mutate(invalid)
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_cleanup_request(invalid)

    def test_run_id_length_matches_gke_cluster_name_limit(self):
        started = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
        for run_id in ("1" * 8, "1" * 13):
            request = {
                "run_id": run_id,
                "source_revision": "a" * 40,
                "cluster_name": f"fleet-lab-r{run_id}",
                "state_prefix": f"gcp-lab/runs/{run_id}",
                "started_at": started.isoformat(),
                "expires_at": (started + timedelta(seconds=MAX_LAB_SECONDS)).isoformat(),
            }
            self.assertEqual(validate_cleanup_request(request), request)

        too_long = dict(request, run_id="1" * 14)
        too_long["cluster_name"] = f"fleet-lab-r{too_long['run_id']}"
        too_long["state_prefix"] = f"gcp-lab/runs/{too_long['run_id']}"
        with self.assertRaises(ValueError):
            validate_cleanup_request(too_long)

    def test_run_inputs_reject_output_inside_public_checkout(self):
        started = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
        expires = started + timedelta(seconds=MAX_LAB_SECONDS)
        tfvars = {
            "project_id": "private-project-123", "zone": "us-central1-a",
            "node_service_account_id": "fleet-lab-nodes", "machine_type": "e2-standard-2",
            "node_count": 1, "node_disk_size_gb": 30, "resource_plan_reviewed": True,
            "review_project_id": "private-project-123", "review_zone": "us-central1-a",
            "inventory_reference": "private:inventory-1", "quota_reviewed": True,
            "pricing_reviewed": True, "workload_sizing_reference": "private:sizing-1",
            "workload_sizing_reviewed": True, "teardown_owner_reference": "private:owner",
            "inventory_matches_review": True, "reviewed_resource_ceiling": 1,
            "ceiling_matches_review": True, "project_zone_match_reviewed": True,
            "retained_network_name": "fleet-lab-ci-network",
            "cloudsql_enabled": True, "cloudsql_plan_reviewed": True,
            "cloudsql_quota_reviewed": True, "cloudsql_pricing_reviewed": True,
            "cloudsql_inventory_reference": "private:sql-inventory",
        }
        checkout = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=checkout) as folder:
            with self.assertRaises(ValueError):
                write_run_inputs(
                    run_id="37131621545", source_revision="a" * 40,
                    started_at=started.isoformat(), expires_at=expires.isoformat(),
                    state_bucket="private-state-bucket", tfvars_json=json.dumps(tfvars),
                    output_dir=folder,
                )
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_actions_inputs_use_one_reviewed_run_state_and_exact_expiry(self):
        started = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
        expires = started + timedelta(seconds=MAX_LAB_SECONDS)
        tfvars = {
            "project_id": "private-project-123", "zone": "us-central1-a",
            "node_service_account_id": "fleet-lab-nodes", "machine_type": "e2-standard-2",
            "node_count": 1, "node_disk_size_gb": 30, "resource_plan_reviewed": True,
            "review_project_id": "private-project-123", "review_zone": "us-central1-a",
            "inventory_reference": "private:inventory-1", "quota_reviewed": True,
            "pricing_reviewed": True, "workload_sizing_reference": "private:sizing-1",
            "workload_sizing_reviewed": True, "teardown_owner_reference": "private:owner",
            "inventory_matches_review": True, "reviewed_resource_ceiling": 1,
            "ceiling_matches_review": True, "project_zone_match_reviewed": True,
            "retained_network_name": "fleet-lab-ci-network",
            "cloudsql_enabled": True, "cloudsql_plan_reviewed": True,
            "cloudsql_quota_reviewed": True, "cloudsql_pricing_reviewed": True,
            "cloudsql_inventory_reference": "private:sql-inventory",
        }
        with tempfile.TemporaryDirectory() as folder:
            outputs = write_run_inputs(
                run_id="37131621545", source_revision="a" * 40,
                started_at=started.isoformat(), expires_at=expires.isoformat(),
                state_bucket="private-state-bucket", tfvars_json=json.dumps(tfvars),
                output_dir=folder,
            )
            values = json.loads(Path(outputs["tfvars"]).read_text(encoding="utf-8"))
            backend = Path(outputs["backend"]).read_text(encoding="utf-8")
            self.assertEqual(values["cluster_name"], "fleet-lab-r37131621545")
            self.assertEqual(values["teardown_deadline"], expires.isoformat().replace("+00:00", "Z"))
            self.assertEqual(values["retained_network_name"], "fleet-lab-ci-network")
            self.assertGreaterEqual(len(values["database_password"]), 32)
            self.assertIn('prefix = "gcp-lab/runs/37131621545"', backend)
            self.assertEqual(outputs["request"]["source_revision"], "a" * 40)

        for change in (
            {"resource_plan_reviewed": False},
            {"node_count": 2},
            {"review_project_id": "other-project-456"},
        ):
            changed = dict(tfvars, **change)
            with tempfile.TemporaryDirectory() as folder, self.subTest(change=change), self.assertRaises(ValueError):
                write_run_inputs(
                    run_id="37131621545", source_revision="a" * 40,
                    started_at=started.isoformat(), expires_at=expires.isoformat(),
                    state_bucket="private-state-bucket", tfvars_json=json.dumps(changed),
                    output_dir=folder,
                )

    def test_bootstrap_locks_every_kubectl_call_to_dns_endpoint_context(self):
        commands = bootstrap_commands("private-project-123", "us-central1-a", "fleet-lab-r37131621545")
        self.assertEqual(expected_context("private-project-123", "us-central1-a", "fleet-lab-r37131621545"),
                         "gke_private-project-123_us-central1-a_fleet-lab-r37131621545")
        self.assertIn("--dns-endpoint", commands[0])
        kubectl = [cmd for cmd in commands if cmd[0] == "kubectl"]
        self.assertTrue(kubectl)
        self.assertTrue(all(any(arg.startswith("--context=gke_private-project-123_") for arg in cmd) for cmd in kubectl[1:]))
        self.assertEqual(ARGO_MANIFEST_SHA256, "7efe2d6bbc03f63623640f1e4198f16c84009d510fb810ef71e56df1b7614ba9")
        with self.assertRaises(ValueError):
            validate_target("private-project-123", "us-central1-a", "fleet-lab; gcloud projects list")


if __name__ == "__main__":
    unittest.main()
