import math
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from scripts.local_cluster import (
    MIN_DOCKER_CPUS, MIN_DOCKER_MEMORY_GIB, ARGO_VERSION, KIND_NODE_IMAGE,
    can_create_cluster, validate_deletion_target, build_kind_config, bootstrap_commands,
)
from scripts.promote_release import parse_chart_version, parse_commit_sha, parse_immutable_image, validate_promotion, application_manifest, verify_app_checkout
from scripts.local_acceptance import validate_workload_bounds, unique_ride_ids, validate_report, collect_endpoint


class LocalClusterTests(unittest.TestCase):
    def test_cluster_capacity_requires_the_proposed_floor(self):
        self.assertTrue(can_create_cluster(MIN_DOCKER_MEMORY_GIB, MIN_DOCKER_CPUS))
        self.assertFalse(can_create_cluster(MIN_DOCKER_MEMORY_GIB - 1, MIN_DOCKER_CPUS))
        self.assertFalse(can_create_cluster(MIN_DOCKER_MEMORY_GIB, MIN_DOCKER_CPUS - 1))
        for values in ((float('nan'), 6), (float('inf'), 6), (True, 6), (8, True), (-1, 8)):
            with self.subTest(values=values):
                self.assertFalse(can_create_cluster(*values))

    def test_teardown_requires_exact_owned_cluster_confirmation(self):
        self.assertTrue(validate_deletion_target('ottawa-fleet-lab', 'ottawa-fleet-lab'))
        self.assertFalse(validate_deletion_target('other-cluster', 'ottawa-fleet-lab'))
        self.assertFalse(validate_deletion_target('ottawa-fleet-lab', ''))

    def test_bootstrap_uses_explicit_context_and_immutable_upstream_pins(self):
        config = build_kind_config()
        self.assertIn('kind: Cluster', config)
        self.assertRegex(KIND_NODE_IMAGE, r'^kindest/node:v\d+\.\d+\.\d+@sha256:[a-f0-9]{64}$')
        self.assertRegex(ARGO_VERSION, r'^v\d+\.\d+\.\d+$')
        commands = bootstrap_commands()
        self.assertIn('kind create cluster --name ottawa-fleet-lab', ' '.join(commands))
        self.assertIn('--context kind-ottawa-fleet-lab', ' '.join(commands))
        self.assertNotIn('stable/manifests', ' '.join(commands))


class ReleasePinTests(unittest.TestCase):
    def test_release_inputs_require_immutable_artifacts(self):
        digest = 'a' * 64
        image = f'ghcr.io/example/app/web@sha256:{digest}'
        self.assertEqual(parse_immutable_image(image), image)
        for invalid in ('ghcr.io/example/app/web:latest', 'ghcr.io/example/app/web@sha256:' + '0' * 64):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                parse_immutable_image(invalid)
        self.assertEqual(parse_chart_version('0.1.0'), '0.1.0')
        with self.assertRaises(ValueError):
            parse_chart_version('main')
        self.assertEqual(parse_commit_sha('a' * 40), 'a' * 40)
        with self.assertRaises(ValueError):
            parse_commit_sha('HEAD')

    def _promotion(self):
        return {
            'chart': {'repository': 'https://github.com/ANISHG-26/ottawa-fleet-app.git', 'name': 'charts/ottawa-fleet', 'version': '1.2.3'},
            'source': {'repository': 'https://github.com/ANISHG-26/ottawa-fleet-app.git', 'revision': 'a' * 40},
            'images': {name: {'reference': 'ghcr.io/anishg-26/ottawa-fleet-app/' + path + '@sha256:' + 'abcdef'[i] * 64,
                              'sourceCommit': 'a' * 40, 'architecture': 'amd64'}
                       for i, (name, path) in enumerate((('dbInit', 'db-init'), ('fleetApi', 'fleet-api'), ('rideApi', 'ride-api'), ('worker', 'assignment-worker'), ('scenarioRunner', 'scenario-runner'), ('web', 'web')))},
            'database': {'existingSecret': 'fleet-database'},
            'rollback': {'previousCompatibleVersion': '1.2.2', 'migrationBackwardCompatible': True},
        }

    def test_promotion_requires_full_pins_compatibility_and_external_secret(self):
        promotion = self._promotion()
        validate_promotion(promotion)
        manifest = application_manifest(promotion)
        self.assertEqual(manifest['spec']['destination']['namespace'], 'fleet-app')
        self.assertEqual(manifest['spec']['source']['targetRevision'], 'a' * 40)
        bad = self._promotion()
        bad['images']['worker']['reference'] = 'ghcr.io/example/worker:latest'
        with self.assertRaises(ValueError):
            validate_promotion(bad)

    def test_promotion_checks_chart_version_at_the_exact_clean_source_commit(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            chart = root / 'charts' / 'ottawa-fleet'
            chart.mkdir(parents=True)
            (chart / 'Chart.yaml').write_text('apiVersion: v2\nname: ottawa-fleet\nversion: 1.2.3\n', encoding='utf-8')
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'user.name=Tests', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'release fixture'], check=True)
            subprocess.run(['git', '-C', str(root), 'remote', 'add', 'origin', 'https://github.com/ANISHG-26/ottawa-fleet-app.git'], check=True)
            revision = subprocess.run(['git', '-C', str(root), 'rev-parse', 'HEAD'], check=True, capture_output=True, text=True).stdout.strip()
            promotion = self._promotion()
            promotion['source']['revision'] = revision
            for image in promotion['images'].values():
                image['sourceCommit'] = revision
            verify_app_checkout(promotion, str(root))
            with self.assertRaises(ValueError):
                verify_app_checkout(self._promotion(), str(root))
        bad = self._promotion()
        bad['rollback']['migrationBackwardCompatible'] = False
        with self.assertRaises(ValueError):
            validate_promotion(bad)


def complete_report():
    endpoints = {
        'ui': '<html>operator</html>', 'fleet-ready': '{"status":"ok"}',
        'fleet': '{"items":[{"vehicle_id":"vehicle-001"}],"next_cursor":null,"as_of":"2026-01-01T00:00:00Z"}',
        'fleet-metrics': 'fleet_http_requests_total 12\nfleet_http_request_duration_seconds_bucket{le="0.1"} 12\n',
        'ride-ready': '{"status":"ok"}',
        'rides': '{"items":[{"ride_id":"ride-001"}],"next_cursor":null}',
        'ride-metrics': 'ride_pending_jobs 0\n',
    }
    return {
        'mode': 'compose', 'status': 'accepted', 'application_commit': 'a' * 40, 'observed_at': '2026-01-01T00:00:00Z',
        'workload': {'rides': 10, 'workers': 1, 'duration_seconds': 60},
        'hardware': {'cpu_count': 8, 'memory_bytes': 8 * 1024**3},
        'resources': {'scope': 'compose-app-stack', 'cpu_percent': 22.5, 'memory_bytes': 64 * 1024**2},
        'endpoints': {k: {'status_code': 200, 'body': v, 'elapsed_ms': 3.2} for k, v in endpoints.items()},
        'observations': {'completed_rides': 10, 'duplicate_ride_ids': 0, 'backlog_before_restart': 2,
                         'backlog_after_restart': 0, 'recovery_seconds': 3.2, 'request_errors': 0, 'p95_latency_ms': 8.0},
        'limitations': [],
    }


class AcceptanceEvidenceTests(unittest.TestCase):
    def test_workload_bounds_and_unique_ids(self):
        validate_workload_bounds(10, 1, 60)
        for values in ((0, 1, 60), (101, 1, 60), (10, 0, 60), (10, 1, 61)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_workload_bounds(*values)
        unique_ride_ids([{'ride_id': 'ride-001'}, {'ride_id': 'ride-002'}])
        with self.assertRaises(ValueError):
            unique_ride_ids([{'ride_id': 'ride-001'}, {'ride_id': 'ride-001'}])

    def test_complete_compose_report_validates_but_mixed_mode_cannot_claim_acceptance(self):
        validate_report(complete_report())
        partial = complete_report()
        partial['mode'] = 'mixed-native-docker-non-compose'
        partial['status'] = 'partial'
        partial['limitations'] = ['not integrated Compose']
        with self.assertRaises(ValueError):
            validate_report(partial)

    def test_missing_metrics_duplicate_ids_and_unresolved_limits_fail(self):
        for mutate in (
            lambda r: r['endpoints'].pop('fleet-metrics'),
            lambda r: r['endpoints']['rides'].update(body='{"items":[{"ride_id":"x"},{"ride_id":"x"}]}'),
            lambda r: r.update(limitations=['outage evidence not collected']),
        ):
            report = complete_report()
            mutate(report)
            with self.assertRaises(ValueError):
                validate_report(report)

    def test_negative_and_nonfinite_observations_fail(self):
        for value in (-1, math.inf, math.nan):
            report = complete_report()
            report['observations']['p95_latency_ms'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_report(report)
        for update in (
            lambda r: r['observations'].update(backlog_before_restart=True),
            lambda r: r['resources'].update(memory_bytes=0),
            lambda r: r.update(application_commit='0' * 40),
            lambda r: r.update(workload={'rides': 1.5, 'workers': 1, 'duration_seconds': 1}),
        ):
            report = complete_report()
            update(report)
            with self.assertRaises(ValueError):
                validate_report(report)
        with self.assertRaises(ValueError):
            validate_report({'workload': []})

    def test_collector_rejects_external_endpoints_oversized_caps_and_redirects(self):
        with self.assertRaises(ValueError):
            collect_endpoint('http://example.com/health')
        with self.assertRaises(ValueError):
            collect_endpoint('http://127.0.0.1/health', max_bytes=10_000_000)

        class Redirect(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(302)
                self.send_header('Location', 'http://example.com/')
                self.end_headers()
            def log_message(self, *_args):
                pass

        server = HTTPServer(('127.0.0.1', 0), Redirect)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(ValueError):
                collect_endpoint(f'http://127.0.0.1:{server.server_port}/')
        finally:
            server.shutdown()
            thread.join()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
