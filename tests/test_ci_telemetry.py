"""Behavior checks for automatically installed and verified lab telemetry."""
import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts import ci_telemetry as telemetry

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 10, 21, tzinfo=timezone.utc)


class TelemetryTests(unittest.TestCase):
    def test_capacity_reserves_monitoring_and_one_web_surge(self):
        nodes = [{'metadata': {'name': 'node'}, 'status': {'allocatable': {'cpu': '1930m', 'memory': '6Gi'}, 'conditions': [{'type': 'Ready', 'status': 'True'}]}}]
        pods = [{'spec': {'nodeName': 'node', 'containers': [{'resources': {'requests': {'cpu': '1500m', 'memory': '1Gi'}}}]}, 'status': {'phase': 'Running'}}]
        with self.assertRaisesRegex(ValueError, 'headroom'):
            telemetry.check_capacity(nodes, pods)
        pods[0]['spec']['containers'][0]['resources']['requests']['cpu'] = '1400m'
        self.assertGreaterEqual(telemetry.check_capacity(nodes, pods)['free_cpu_millis'], 450)

    def test_capacity_counts_init_and_overhead_and_ignores_finished_pods(self):
        nodes = [{'metadata': {'name': 'node'}, 'status': {'allocatable': {'cpu': '2', 'memory': '6Gi'}, 'conditions': [{'type': 'Ready', 'status': 'True'}]}}]
        spec = {'nodeName': 'node', 'containers': [{'resources': {'requests': {'cpu': '100m'}}}],
                'initContainers': [{'resources': {'requests': {'cpu': '1600m'}}}], 'overhead': {'cpu': '10m'}}
        with self.assertRaises(ValueError):
            telemetry.check_capacity(nodes, [{'spec': spec, 'status': {'phase': 'Running'}}])
        self.assertEqual(telemetry.check_capacity(nodes, [{'spec': spec, 'status': {'phase': 'Succeeded'}}])['free_cpu_millis'], 2000)

    def test_capacity_refuses_unexpected_monitoring_workloads_on_retry(self):
        nodes = [{'metadata': {'name': 'node'}, 'status': {'allocatable': {'cpu': '2', 'memory': '6Gi'}, 'conditions': [{'type': 'Ready', 'status': 'True'}]}}]
        pod = {'metadata': {'namespace': 'observability', 'labels': {'app.kubernetes.io/name': 'unrelated'}}, 'spec': {'containers': [{'resources': {'requests': {'cpu': '10m'}}}]}, 'status': {'phase': 'Running'}}
        with self.assertRaisesRegex(ValueError, 'unexpected'):
            telemetry.check_capacity(nodes, [pod])
        pod['metadata']['labels']['app.kubernetes.io/name'] = 'grafana'
        pod['spec']['containers'][0]['resources']['requests']['cpu'] = '900m'
        with self.assertRaisesRegex(ValueError, 'budget'):
            telemetry.check_capacity(nodes, [pod])

    def test_grafana_request_refuses_remote_base_and_redirects(self):
        with self.assertRaises(ValueError):
            telemetry._grafana_json('https://example.com', 'secret', '/grafana/api/health')
        with self.assertRaises(ValueError):
            telemetry._NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com')

    def test_signal_check_requires_real_rows_and_no_query_error(self):
        for result in ({}, {'results': {'A': {'frames': []}}}, {'results': {'A': {'error': 'failed', 'frames': [{'data': {'values': [[1]]}}]}}}):
            self.assertFalse(telemetry.query_has_rows(result))
        self.assertTrue(telemetry.query_has_rows({'results': {'A': {'frames': [{'data': {'values': [[1], [2]]}}]}}}))

    def test_expired_lease_prevents_all_cluster_actions(self):
        with self.assertRaisesRegex(RuntimeError, 'expiry'), patch.object(telemetry, '_run') as run:
            telemetry.deploy(project='private-project-123', zone='us-central1-a', cluster='fleet-lab-r12345678901', kubeconfig='private-kubeconfig', expires_at=NOW.isoformat(), root=ROOT, now=lambda: NOW)
        run.assert_not_called()

    def bootstrap(self, query_failure=False, create_secret=False, transient_probe=False):
        commands, http = [], []
        password = 'private-password-' + 'x' * 40
        secret = {'metadata': {'labels': {'platform.ottawa-fleet/owner': 'ci-lgtm'}}, 'data': {'password': base64.b64encode(password.encode()).decode()}}
        def runner(command, **kwargs):
            commands.append((command, kwargs))
            stdout = ''
            if 'nodes' in command:
                stdout = json.dumps({'items': [{'metadata': {'name': 'node'}, 'status': {'allocatable': {'cpu': '4', 'memory': '8Gi'}, 'conditions': [{'type': 'Ready', 'status': 'True'}]}}]})
            elif 'pods' in command:
                stdout = json.dumps({'items': []})
            elif 'secret' in command and 'get' in command:
                stdout = '' if create_secret else json.dumps(secret)
            elif transient_probe and '--raw' in command and not any('--raw' in c for c, _ in commands[:-1]):
                return subprocess.CompletedProcess(command, 1, 'private raw response', '')
            return subprocess.CompletedProcess(command, 0, stdout, '')
        @contextmanager
        def forward(*_):
            yield 'http://127.0.0.1:13000'
        def request(base, supplied_password, path, payload=None, **kwargs):
            if not create_secret:
                self.assertEqual(supplied_password, password)
            http.append((path, payload))
            if path.endswith('/api/health'):
                return {'database': 'ok'}
            if path.endswith('/api/datasources'):
                return [{'uid': uid} for uid in ('mimir', 'loki', 'tempo')]
            if '/proxy/uid/mimir/' in path:
                return {'status': 'success', 'data': {'result': [{'metric': {'service': service}, 'value': [0, '1']} for service in ('fleet-api', 'ride-api', 'assignment-worker')]}}
            return {'results': {'A': {'frames': [] if query_failure else [{'data': {'values': [[1]]}}]}}}
        current = [NOW]
        def sleep(seconds):
            current[0] += timedelta(seconds=seconds)
        with patch.object(telemetry, '_grafana_json', side_effect=request):
            result = telemetry.deploy(project='private-project-123', zone='us-central1-a', cluster='fleet-lab-r12345678901', kubeconfig='private-kubeconfig', expires_at=(NOW + timedelta(seconds=20)).isoformat(), root=ROOT, runner=runner, now=lambda: current[0], sleep=sleep, forward=forward)
        return result, commands, http, password

    def test_bootstrap_uses_exact_context_private_secret_and_all_three_queries(self):
        result, commands, http, password = self.bootstrap()
        self.assertEqual(result['signals'], ['metrics', 'logs', 'traces'])
        self.assertEqual(len([p for p, body in http if body and p.endswith('/api/ds/query')]), 3)
        for command, kwargs in commands:
            self.assertIn('--context=gke_private-project-123_us-central1-a_fleet-lab-r12345678901', command)
            self.assertNotIn(password, ' '.join(command))
        self.assertTrue(any('observability/ci' in str(c) for c, _ in commands))
        self.assertFalse(any('create' in c and 'secret' in c for c, _ in commands), 'retries must reuse the existing credential')

    def test_new_secret_goes_only_through_captured_stdin(self):
        _, commands, _, _ = self.bootstrap(create_secret=True)
        writes = [(c, kw) for c, kw in commands if c[-3:] == ['create', '-f', '-']]
        self.assertEqual(len(writes), 1)
        c, kwargs = writes[0]
        secret = json.loads(kwargs['input'])
        value = base64.b64decode(secret['data']['password']).decode()
        self.assertGreaterEqual(len(value), 32)
        self.assertNotIn(value, ' '.join(c))

    def test_missing_signal_never_reports_ready_and_hides_query_details(self):
        with self.assertRaisesRegex(RuntimeError, 'expiry') as caught:
            self.bootstrap(query_failure=True)
        self.assertNotIn('private-password', str(caught.exception))

    def test_transient_service_probe_is_retried_within_the_lease(self):
        result, _, _, _ = self.bootstrap(transient_probe=True)
        self.assertEqual(result['signals'], ['metrics', 'logs', 'traces'])


if __name__ == '__main__':
    unittest.main()
