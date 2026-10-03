"""Exercise Terraform's mock-provider contract tests without contacting GCP."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TERRAFORM_ROOT = ROOT / "terraform" / "lab"
TERRAFORM = os.environ.get("TERRAFORM_BIN") or shutil.which("terraform")
GOOGLE_PROVIDER_DIR = TERRAFORM_ROOT / ".terraform" / "providers" / "registry.terraform.io" / "hashicorp" / "google"


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


if __name__ == "__main__":
    unittest.main()
