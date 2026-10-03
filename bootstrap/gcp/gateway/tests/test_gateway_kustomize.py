import pathlib
import shutil
import subprocess
import unittest


GATEWAY_DIR = pathlib.Path(__file__).resolve().parents[1]
PLATFORM_DIR = GATEWAY_DIR.parents[2]


class GatewayKustomizeContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        kubectl = shutil.which("kubectl")
        if kubectl is None:
            raise unittest.SkipTest("kubectl is required to render the gateway kustomization")
        result = subprocess.run(
            [kubectl, "kustomize", str(GATEWAY_DIR)],
            cwd=PLATFORM_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.gateway = result.stdout
        argo = subprocess.run(
            [kubectl, "kustomize", str(PLATFORM_DIR / "bootstrap" / "gcp" / "argo")],
            cwd=PLATFORM_DIR,
            check=True,
            capture_output=True,
            text=True,
        )
        cls.argo = argo.stdout

    def test_only_web_ui_and_secure_console_routes_are_configured(self):
        self.assertIn("web.fleet-app.svc.cluster.local:8080", self.gateway)
        self.assertIn("grafana.observability.svc.cluster.local:3000", self.gateway)
        self.assertIn("argocd-server.argocd.svc.cluster.local:443", self.gateway)
        self.assertNotIn("argocd-server.argocd.svc.cluster.local:80", self.gateway)
        self.assertNotIn("redis", self.gateway.lower())
        self.assertIn('port: 443', self.gateway)
        self.assertIn('return 308 https://$host$request_uri', self.gateway)

    def test_gateway_is_pinned_nonroot_and_has_restricted_egress(self):
        self.assertIn(
            "nginxinc/nginx-unprivileged:1.30-alpine@sha256:ed04ec1ff34502c339ee5c3ae3f855442398edc1d05591e2b98981dcbbd20b1e",
            self.gateway,
        )
        self.assertIn("runAsNonRoot: true", self.gateway)
        self.assertIn("automountServiceAccountToken: false", self.gateway)
        self.assertIn("readOnlyRootFilesystem: true", self.gateway)
        self.assertIn("policyTypes:\n  - Ingress\n  - Egress", self.gateway)
        self.assertNotIn("egress: [{}]", self.gateway)

    def test_argo_path_is_configured_without_disabling_tls(self):
        self.assertIn("server.rootpath: /argo", self.argo)
        self.assertIn("server.basehref: /argo", self.argo)
        self.assertNotIn("server.insecure: \"true\"", self.argo)

    def test_public_ingress_is_closed_until_private_reviewer_allowlist_is_supplied(self):
        self.assertIn("loadBalancerSourceRanges:\n  - 0.0.0.0/32", self.gateway)
        self.assertNotIn("0.0.0.0/0", self.gateway)


if __name__ == "__main__":
    unittest.main()
