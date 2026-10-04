"""Private command diagnostics are bounded and never leaked to public errors."""
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cleanup_execute, ci_lab
from scripts.private_diagnostics import MAX_DIAGNOSTIC_BYTES, upload_failure_diagnostic


class PrivateDiagnosticTests(unittest.TestCase):
    prefix = "gs://private-bucket/gcp-lab/runs/37214476746/diagnostics"

    def test_upload_is_run_scoped_bounded_and_quiet(self):
        secret = "PRIVATE_SENTINEL_DO_NOT_LOG"
        observed = {}

        def uploader(command, **kwargs):
            observed["command"] = command
            observed["bytes"] = Path(command[-2]).read_bytes()
            return subprocess.CompletedProcess(command, 0, "", "")

        saved = upload_failure_diagnostic(prefix=self.prefix, stage="terraform-apply",
            returncode=1, stdout="x" * (MAX_DIAGNOSTIC_BYTES * 2) + secret, stderr="provider error",
            runner=uploader)
        self.assertTrue(saved)
        self.assertTrue(observed["command"][0:3] == ["gcloud", "storage", "cp"])
        self.assertIn("--if-generation-match=0", observed["command"])
        self.assertTrue(observed["command"][-1].startswith(self.prefix + "/"))
        self.assertLessEqual(len(observed["bytes"]), MAX_DIAGNOSTIC_BYTES)
        self.assertIn(secret.encode(), observed["bytes"])

    def test_upload_failure_preserves_sanitized_ci_failure(self):
        secret = "PRIVATE_SENTINEL_DO_NOT_LOG"

        def runner(command, **kwargs):
            if command[0] == "terraform":
                return subprocess.CompletedProcess(command, 1, secret, "provider detail")
            return subprocess.CompletedProcess(command, 1, "", "upload denied")

        with patch.object(ci_lab, "upload_failure_diagnostic", side_effect=lambda **kw:
                          upload_failure_diagnostic(**kw)):
            with self.assertRaisesRegex(RuntimeError, "private diagnostic unavailable") as caught:
                ci_lab._run(["terraform", "apply"], cwd=Path("."), runner=runner,
                            diagnostic_prefix=self.prefix, stage="terraform-apply")
        self.assertNotIn(secret, str(caught.exception))

    def test_tempfile_unlink_failure_preserves_static_ci_failure(self):
        def runner(command, **kwargs):
            if command[0] == "terraform":
                return subprocess.CompletedProcess(command, 1, "", "provider detail")
            return subprocess.CompletedProcess(command, 1, "", "upload denied")

        with patch.object(Path, "unlink", side_effect=OSError("unlink denied")):
            with self.assertRaisesRegex(RuntimeError, "provisioning command failed.*private diagnostic unavailable"):
                ci_lab._run(["terraform", "apply"], cwd=Path("."), runner=runner,
                            diagnostic_prefix=self.prefix, stage="terraform-apply")

    def test_cleanup_destroy_failure_uploads_and_reports_only_static_status(self):
        secret = "PRIVATE_SENTINEL_DO_NOT_LOG"
        calls = []

        def runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, secret, "provider detail")

        def upload(**kwargs):
            calls.append(kwargs)
            return True

        with patch.object(cleanup_execute, "upload_failure_diagnostic", side_effect=upload):
            with self.assertRaisesRegex(cleanup_execute.CleanupCommandFailure,
                                        "terraform-destroy.*private diagnostic saved") as caught:
                cleanup_execute.run(["terraform", "destroy"], runner=runner,
                    diagnostic_prefix=self.prefix, stage="terraform-destroy")
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["prefix"], self.prefix)
        self.assertNotIn(secret, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
