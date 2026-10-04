"""Exercise Terraform's mock-provider contract tests without contacting GCP."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_ROOT = ROOT / "terraform" / "lab"
TERRAFORM = os.environ.get("TERRAFORM_BIN") or shutil.which("terraform")
GOOGLE_PROVIDER_DIR = TERRAFORM_ROOT / ".terraform" / "providers" / "registry.terraform.io" / "hashicorp" / "google"
AUTOMATION_ROOT = ROOT / "terraform" / "automation"


@unittest.skipUnless(TERRAFORM, "Terraform CLI is required for the offline mock-provider tests")
class TerraformBoundsTests(unittest.TestCase):
    def test_gke_lab_bounds_and_review_gate(self) -> None:
        if not any(GOOGLE_PROVIDER_DIR.rglob("terraform-provider-google*")):
            self.skipTest("the Google provider is not initialized; run terraform init -backend=false first")

        result = subprocess.run(
            [TERRAFORM, "test", "-no-color"],
            cwd=TERRAFORM_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=180,
        )

        self.assertEqual(
            result.returncode,
            0,
            msg=f"terraform test failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
        )


class TerraformAutomationIamBoundsTests(unittest.TestCase):
    def test_ephemeral_network_role_can_list_gke_managers_without_manager_writes(self) -> None:
        config = (AUTOMATION_ROOT / "main.tf").read_text(encoding="utf-8")
        role = re.search(r'resource "google_project_iam_custom_role" "network_editor"\s*\{(?P<body>.*?)\n\}', config, re.DOTALL).group('body')
        self.assertIn('"compute.networks.updatePolicy"', role)
        self.assertIn('"compute.instanceGroupManagers.list"', role)
        for permission in (
            'compute.instanceGroupManagers.create',
            'compute.instanceGroupManagers.update',
            'compute.instanceGroupManagers.delete',
            'compute.networks.create',
            'compute.networks.delete',
            'compute.networks.setIamPolicy',
        ):
            self.assertNotIn('"' + permission + '"', role)

    def test_exact_immutable_oidc_subject_keeps_main_workflow_environment_boundary(self) -> None:
        config = (AUTOMATION_ROOT / "main.tf").read_text(encoding="utf-8")
        self.assertIn('repo:ANISHG-26@${var.github_repository_owner_id}/ottawa-fleet-platform@${var.github_repository_id}:environment:gcp-lab', config)
        for claim in ('repository_id', 'repository_owner_id', 'repository', 'ref', 'workflow_ref', 'sub'):
            self.assertIn('assertion.' + claim + ' ==', config)
        self.assertIn("assertion.ref == 'refs/heads/main'", config)
        self.assertIn('/.github/workflows/lab-deploy.yml@refs/heads/main', config)

    def test_function_builder_copy_access_is_bucket_and_prefix_scoped_before_function(self) -> None:
        config = (AUTOMATION_ROOT / "main.tf").read_text(encoding="utf-8")
        grant_match = re.search(
            r'resource "google_project_iam_member" "function_builder_copied_source_read"\s*\{(?P<body>.*?)\n\}',
            config,
            re.DOTALL,
        )
        self.assertIsNotNone(grant_match, "missing bucket-scoped Cloud Functions source-copy grant")
        grant = grant_match.group("body")

        self.assertIn('project = var.project_id', grant)
        self.assertIn('role    = "roles/storage.objectViewer"', grant)
        self.assertIn(
            'function_build_source_bucket = "gcf-v2-sources-${var.project_number}-${var.cloud_build_location}"',
            config,
        )
        self.assertIn(
            'expression  = "resource.name.startsWith(\\"projects/_/buckets/${local.function_build_source_bucket}/objects/${local.function_name}/\\")"',
            grant,
        )
        self.assertIn('depends_on = [google_project_service.automation]', grant)
        project_bindings = re.findall(
            r'resource "google_project_iam_member"\s+"[^\"]+"\s*\{(?P<body>.*?)\n\}',
            config,
            re.DOTALL,
        )
        storage_viewer_bindings = [
            body for body in project_bindings if 'role    = "roles/storage.objectViewer"' in body
        ]
        self.assertEqual(len(storage_viewer_bindings), 1)
        self.assertIn(
            'expression  = "resource.name.startsWith(\\"projects/_/buckets/${local.function_build_source_bucket}/objects/${local.function_name}/\\")"',
            storage_viewer_bindings[0],
        )

        function_match = re.search(
            r'resource "google_cloudfunctions2_function" "shutdown"\s*\{(?P<body>.*?)\n\}',
            config,
            re.DOTALL,
        )
        self.assertIsNotNone(function_match, "missing shutdown function resource")
        function = function_match.group("body")
        self.assertIn("google_project_iam_member.function_builder_copied_source_read", function)


if __name__ == "__main__":
    unittest.main()
