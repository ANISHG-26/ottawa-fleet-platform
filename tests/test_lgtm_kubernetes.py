"""Offline safeguards for the optional, single-node GKE telemetry overlay."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
K8S = ROOT / "observability" / "kubernetes"


class KubernetesTelemetryTests(unittest.TestCase):
    def test_bounded_single_pod_stack_keeps_the_reviewed_request_budget(self):
        manifests = "\n".join(
            (K8S / name).read_text(encoding="utf-8")
            for name in ("backends.yaml", "grafana.yaml", "alloy.yaml")
        )
        self.assertEqual(
            re.findall(r"image: (grafana/[^\s]+)", manifests),
            [
                "grafana/loki:3.7.0",
                "grafana/tempo:3.0.3",
                "grafana/mimir:3.2.1",
                "grafana/grafana:13.2.2",
                "grafana/alloy:v1.20.1",
            ],
        )
        cpu_requests = [int(value) for value in re.findall(r"requests: \{cpu: (\d+)m, memory: [^}]+\}", manifests)]
        self.assertEqual(cpu_requests, [50, 50, 200, 50, 50])
        self.assertLessEqual(sum(cpu_requests), 400)
        self.assertEqual(manifests.count("replicas: 1"), 5)
        self.assertEqual(manifests.count("strategy:\n    type: Recreate"), 5)
        self.assertEqual(manifests.count("allowPrivilegeEscalation: false"), 5)
        self.assertEqual(manifests.count("readOnlyRootFilesystem: true"), 5)
        self.assertEqual(manifests.count("runAsNonRoot: true"), 5)
        self.assertEqual(manifests.count("runAsUser:"), 5)
        self.assertEqual(manifests.count("name: tmp"), 10)
        self.assertNotIn("type: LoadBalancer", manifests)

    def test_prometheus_loki_and_tempo_wiring_matches_the_app_contract(self):
        alloy = (K8S / "alloy.k8s.alloy").read_text(encoding="utf-8")
        for target in (
            "fleet-api.fleet-app.svc.cluster.local:8080",
            "ride-api.fleet-app.svc.cluster.local:8081",
            "assignment-worker.fleet-app.svc.cluster.local:8082",
        ):
            with self.subTest(target=target):
                self.assertIn(target, alloy)
        self.assertIn('endpoint = "0.0.0.0:4318"', alloy)
        self.assertIn("otelcol.exporter.otlp \"tempo\"", alloy)
        self.assertIn("prometheus.remote_write \"mimir\"", alloy)
        self.assertIn("loki.source.kubernetes \"app_logs\"", alloy)
        self.assertIn('names = ["fleet-app"]', alloy)
        self.assertIn('regex = "fleet-api|ride-api|assignment-worker"', alloy)

    def test_read_only_backends_have_bounded_writable_scratch_paths(self):
        backends = (K8S / "backends.yaml").read_text(encoding="utf-8")
        self.assertIn("workingDir: /data", backends)
        self.assertIn("mountPath: /data", backends)
        self.assertIn("mountPath: /var/tempo", backends)
        self.assertIn("name: scheduler-data", backends)
        self.assertIn("emptyDir: {sizeLimit: 64Mi}", backends)

    def test_dashboard_datasources_and_provisioning_are_kept_in_sync(self):
        pairs = (
            ("loki.yaml", "../loki/config.yaml"),
            ("tempo.yaml", "../tempo/config.yaml"),
            ("mimir.yaml", "../mimir/config.yaml"),
            (
                "grafana-datasources.yaml",
                "../grafana/provisioning/datasources/datasources.yaml",
            ),
            (
                "grafana-dashboards.yaml",
                "../grafana/provisioning/dashboards/dashboards.yaml",
            ),
            ("ottawa-fleet.json", "../grafana/dashboards/ottawa-fleet.json"),
        )
        for k8s_name, compose_name in pairs:
            with self.subTest(k8s_name=k8s_name):
                self.assertEqual(
                    (K8S / k8s_name).read_text(encoding="utf-8"),
                    (K8S / compose_name).resolve().read_text(encoding="utf-8"),
                )
        sources = (K8S / "grafana-datasources.yaml").read_text(encoding="utf-8")
        for datasource_uid in ("mimir", "loki", "tempo"):
            with self.subTest(datasource=datasource_uid):
                self.assertIn(f"uid: {datasource_uid}", sources)

    def test_grafana_is_subpath_ready_and_logging_rbac_is_namespace_limited(self):
        grafana = (K8S / "grafana.yaml").read_text(encoding="utf-8")
        self.assertIn("https://GATEWAY_IP_PLACEHOLDER/grafana/", grafana)
        self.assertIn("GF_SERVER_SERVE_FROM_SUB_PATH", grafana)
        self.assertIn("GF_SECURITY_COOKIE_SECURE", grafana)
        self.assertIn("GF_AUTH_ANONYMOUS_ENABLED", grafana)
        self.assertIn('{name: GF_PLUGINS_PREINSTALL_AUTO_UPDATE, value: "false"}', grafana)
        self.assertIn("runAsNonRoot: true", grafana)
        self.assertIn("readOnlyRootFilesystem: true", grafana)
        self.assertIn("type: Recreate", grafana)
        self.assertIn("/grafana/api/health", grafana)
        self.assertIn("path: datasources/datasources.yaml", grafana)
        self.assertIn("path: dashboards/dashboards.yaml", grafana)
        self.assertIn("secretKeyRef: {name: grafana-admin, key: password}", grafana)
        self.assertIn("app.kubernetes.io/name: grafana", grafana)

        rbac = (K8S / "alloy-rbac.yaml").read_text(encoding="utf-8")
        self.assertEqual(rbac.count("namespace: fleet-app"), 2)
        self.assertIn('resources: ["pods"]', rbac)
        self.assertIn('resources: ["pods/log"]', rbac)
        self.assertIn("verbs: [\"get\"]", rbac)
        self.assertNotIn("ClusterRole", rbac)
        self.assertIn("namespace: observability", rbac)


if __name__ == "__main__":
    unittest.main()
