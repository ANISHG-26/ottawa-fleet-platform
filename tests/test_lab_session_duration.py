"""Selected lab duration stays fixed through durable provisioning and cleanup."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts import ci_lab, lab_cleanup
from functions.lab_shutdown.scripts_validator import validate_cleanup_request as function_validate
from tests.test_ci_lab import environment


class LabSessionDurationTests(unittest.TestCase):
    def test_choice_sets_exact_expiry_from_original_start_including_day_rollover(self):
        for hours in ('2', '4', '6'):
            with self.subTest(hours=hours):
                start, expires = ci_lab.expiry_from_run_start('2026-10-20T23:10:00Z', hours)
                self.assertEqual(start, '2026-10-20T23:10:00Z')
                self.assertEqual(datetime.fromisoformat(expires.replace('Z', '+00:00')),
                                 datetime(2026, 10, 20, 23, 10, tzinfo=timezone.utc) + timedelta(hours=int(hours)))
        self.assertEqual(ci_lab.expiry_from_run_start('2026-10-20T12:00:00Z')[1], '2026-10-20T14:00:00Z')

    def test_invalid_or_noncanonical_choices_are_rejected(self):
        for choice in ('', '0', '1', '3', '5', '7', '24', '4.0', ' 4', '04', '6;echo x', 4, True, None):
            with self.subTest(choice=choice), self.assertRaises(ValueError):
                ci_lab.expiry_from_run_start('2026-10-20T12:00:00Z', choice)

    def test_both_cleanup_consumers_accept_only_exact_2_4_6_hour_requests(self):
        start = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
        request = {'run_id': '37131621545', 'source_revision': 'a' * 40,
                   'cluster_name': 'fleet-lab-r37131621545', 'state_prefix': 'gcp-lab/runs/37131621545',
                   'started_at': start.isoformat()}
        for seconds in (-7200, 0, 3600, 7200, 7201, 10800, 14400, 18000, 21600, 21601, 86400):
            candidate = dict(request, expires_at=(start + timedelta(seconds=seconds)).isoformat())
            for validate in (lab_cleanup.validate_cleanup_request, function_validate):
                with self.subTest(seconds=seconds, validate=validate.__module__):
                    if seconds in (7200, 14400, 21600):
                        self.assertEqual(validate(candidate), candidate)
                    else:
                        with self.assertRaises(ValueError):
                            validate(candidate)

    def test_long_sessions_fail_before_cloud_calls_until_cleanup_is_activated(self):
        root = Path(__file__).resolve().parents[1]
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        for hours, cap in (('4', None), ('6', '2'), ('6', '4'), ('4', '3'), ('bad', '6')):
            env = dict(environment(), GITHUB_SHA=head, LAB_SESSION_HOURS=hours)
            if cap is not None:
                env['LAB_CLEANUP_MAX_SESSION_HOURS'] = cap
            with self.subTest(hours=hours, cap=cap), \
                 patch.object(ci_lab, 'fetch_run_started_at') as fetch, \
                 patch.object(ci_lab, '_access_token') as token, \
                 patch.object(ci_lab, '_upload') as upload, \
                 patch.object(ci_lab, '_create_task') as task:
                with self.assertRaises((ValueError, RuntimeError)):
                    ci_lab.run_pipeline(env, source_root=root)
                for call in (fetch, token, upload, task):
                    call.assert_not_called()

    def test_selected_expiry_reaches_request_tfvars_task_app_and_telemetry_without_drift(self):
        root = Path(__file__).resolve().parents[1]
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root, capture_output=True, text=True, check=True).stdout.strip()
        start = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        for hours in ('2', '4', '6'):
            env = dict(environment(), GITHUB_SHA=head, LAB_SESSION_HOURS=hours, LAB_CLEANUP_MAX_SESSION_HOURS='6')
            events, uploaded, tasks, apps = [], {}, [], []
            def archive(*, output_path, **kwargs):
                Path(output_path).write_bytes(b'sanitized fake archive')
                return Path(output_path)
            def upload(path, uri, runner):
                events.append('upload')
                if path.name in ('cleanup-request.json', 'terraform.tfvars.json'):
                    uploaded[path.name] = json.loads(path.read_text())
            def task(**kwargs):
                events.append('task')
                tasks.append(kwargs)
            def app(**kwargs):
                apps.append(kwargs)
                return {'tag': 'v0.2.1', 'sha': 'a' * 40}
            def runner(command, **kwargs):
                if command[:2] == ['terraform', 'apply']:
                    events.append('apply')
                return subprocess.CompletedProcess(command, 0, stdout='', stderr='')
            with self.subTest(hours=hours), \
                 patch.object(ci_lab, 'fetch_run_started_at', return_value=start), \
                 patch.object(ci_lab, 'create_source_archive', side_effect=archive), \
                 patch.object(ci_lab, '_access_token', return_value='fake-token'), \
                 patch.object(ci_lab, 'acquire_active_lease', return_value=('12345', False)), \
                 patch.object(ci_lab, '_upload', side_effect=upload), \
                 patch.object(ci_lab, '_create_task', side_effect=task), \
                 patch('scripts.ci_application.deploy', side_effect=app), \
                 patch('scripts.ci_telemetry.deploy', return_value={'signals': ['metrics', 'logs', 'traces']}) as monitoring:
                result = ci_lab.run_pipeline(env, runner=runner, source_root=root)
            expected = ci_lab.expiry_from_run_start(start, hours)[1]
            self.assertEqual(uploaded['cleanup-request.json']['expires_at'], expected)
            self.assertEqual(uploaded['terraform.tfvars.json']['teardown_deadline'], expected)
            self.assertEqual(tasks[0]['schedule_time'], expected)
            self.assertEqual(apps[0]['expires_at'], expected)
            self.assertEqual(monitoring.call_args.kwargs['expires_at'], expected)
            self.assertTrue(apps[0]['telemetry_enabled'])
            self.assertEqual(result['expires_at'], expected)
            self.assertEqual(result['session_hours'], int(hours))
            self.assertLess(events.index('task'), events.index('apply'))


if __name__ == '__main__':
    unittest.main()
