import unittest

from scripts.local_acceptance import validate_report


def complete_report():
    endpoints = {
        'ui': '<html>operator</html>',
        'fleet-ready': '{"status":"ok"}',
        'fleet': '{"items":[{"vehicle_id":"vehicle-001"}],"next_cursor":null,"as_of":"2026-01-01T00:00:00Z"}',
        'fleet-metrics': 'fleet_http_requests_total 12\n',
        'ride-ready': '{"status":"ok"}',
        'rides': '{"items":[{"ride_id":"ride-001"}],"next_cursor":null}',
        'ride-metrics': 'ride_pending_jobs 0\n',
    }
    return {
        'mode': 'compose', 'status': 'accepted', 'application_commit': 'a' * 40,
        'observed_at': '2026-01-01T00:00:00Z',
        'workload': {'rides': 10, 'workers': 1, 'duration_seconds': 60},
        'hardware': {'cpu_count': 8, 'memory_bytes': 8 * 1024**3},
        'resources': {'scope': 'compose-app-stack', 'cpu_percent': 22.5, 'memory_bytes': 64 * 1024**2},
        'endpoints': {key: {'status_code': 200, 'body': body, 'elapsed_ms': 3.2} for key, body in endpoints.items()},
        'observations': {'completed_rides': 10, 'duplicate_ride_ids': 0, 'backlog_before_restart': 2,
                         'backlog_after_restart': 0, 'recovery_seconds': 3.2, 'request_errors': 0,
                         'p95_latency_ms': 8.0},
        'limitations': [],
    }


class AcceptanceOutcomeTests(unittest.TestCase):
    def test_rejects_empty_fleet(self):
        report = complete_report()
        report['endpoints']['fleet']['body'] = '{"items":[],"next_cursor":null}'
        with self.assertRaisesRegex(ValueError, 'fleet endpoint'):
            validate_report(report)

    def test_rejects_empty_ride_history(self):
        report = complete_report()
        report['endpoints']['rides']['body'] = '{"items":[],"next_cursor":null}'
        with self.assertRaisesRegex(ValueError, 'ride history'):
            validate_report(report)

    def test_rejects_no_completed_rides(self):
        report = complete_report()
        report['observations']['completed_rides'] = 0
        with self.assertRaisesRegex(ValueError, 'at least one completed ride'):
            validate_report(report)

    def test_malformed_fleet_and_ride_items_raise_validation_errors(self):
        malformed = (
            lambda r: r['endpoints']['fleet'].update(body='[]'),
            lambda r: r['endpoints']['fleet'].update(body='{"items":[null]}'),
            lambda r: r['endpoints']['rides'].update(body='{"items":{}}'),
            lambda r: r['endpoints']['rides'].update(body='{"items":[null]}'),
        )
        for mutate in malformed:
            report = complete_report()
            mutate(report)
            with self.subTest(report=report['endpoints']['fleet']['body'] + report['endpoints']['rides']['body']):
                with self.assertRaises(ValueError):
                    validate_report(report)

    def test_realistic_complete_report_remains_accepted(self):
        validate_report(complete_report())


if __name__ == '__main__':
    unittest.main()
