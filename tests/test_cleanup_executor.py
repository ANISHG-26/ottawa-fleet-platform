"""Cleanup acceptance rejects surviving resources and untrusted tool bytes."""
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import cleanup_execute as cleanup


class CleanupExecutorTests(unittest.TestCase):
    def test_gateway_inventory_owns_only_forwarding_rule_for_observed_ip(self):
        network_link = 'projects/synthetic-project/global/networks/retained'
        rules = [
            {'name': 'gateway-run-ip', 'selfLink': 'rules/gateway-run-ip',
             'IPAddress': '203.0.113.12', 'network': network_link},
            {'name': 'other-service-ip', 'selfLink': 'rules/other-service-ip',
             'IPAddress': '203.0.113.99', 'network': network_link},
        ]
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(cleanup.subprocess, 'run', side_effect=[
                    subprocess.CompletedProcess(['gcloud', 'storage', 'cp'], 1, stdout='',
                        stderr='The following URLs matched no objects or files:'),
                    subprocess.CompletedProcess(['gcloud', 'storage', 'cp'], 0, stdout='', stderr='')]):
            def command(args):
                if 'networks' in args:
                    return json.dumps({'selfLink': network_link})
                return json.dumps(rules)
            links = cleanup.save_gateway_inventory(
                bucket='synthetic-bucket', prefix='gcp-lab/runs/12345678',
                network='retained', project='synthetic-project', work=Path(directory),
                command=command, gateway_ips={'203.0.113.12'})
            self.assertEqual(links, {'rules/gateway-run-ip'})

    def test_empty_gateway_ips_with_ambiguous_shared_network_rule_fails_closed(self):
        network_link = 'projects/synthetic-project/global/networks/retained'
        rules = [{'name': 'other-service-ip', 'selfLink': 'rules/other-service-ip',
                  'IPAddress': '203.0.113.99', 'network': network_link}]
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(cleanup.subprocess, 'run', side_effect=[
                    subprocess.CompletedProcess(['gcloud', 'storage', 'cp'], 1, stdout='',
                        stderr='The following URLs matched no objects or files:'),
                    subprocess.CompletedProcess(['gcloud', 'storage', 'cp'], 0, stdout='', stderr='')]):
            def command(args):
                if 'networks' in args:
                    return json.dumps({'selfLink': network_link})
                return json.dumps(rules)
            with self.assertRaisesRegex(RuntimeError, 'cannot identify gateway forwarding rules'):
                cleanup.save_gateway_inventory(
                    bucket='synthetic-bucket', prefix='gcp-lab/runs/12345678',
                    network='retained', project='synthetic-project', work=Path(directory),
                    command=command, gateway_ips=set())
            self.assertFalse((Path(directory) / 'runowned-resources.json').exists())

    def test_gcloud_587_missing_inventory_message_is_treated_as_absent(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(cleanup.subprocess, 'run', side_effect=[
                    subprocess.CompletedProcess(['gcloud', 'storage', 'cp'], 1, stdout='',
                        stderr='The following URLs matched no objects or files:\n'),
                    subprocess.CompletedProcess(['gcloud', 'storage', 'cp'], 0, stdout='', stderr='')]):
            def command(args):
                if 'networks' in args:
                    return '{"selfLink":"projects/synthetic-project/global/networks/retained"}'
                return '[]'
            links = cleanup.save_gateway_inventory(
                bucket='synthetic-bucket', prefix='gcp-lab/runs/12345678',
                network='retained', project='synthetic-project', work=Path(directory),
                command=command)
            self.assertEqual(links, set())
            self.assertTrue((Path(directory) / 'runowned-resources.json').exists())

    def test_permission_denied_reading_inventory_is_not_treated_as_absent(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(cleanup.subprocess, 'run', return_value=subprocess.CompletedProcess(
                    ['gcloud', 'storage', 'cp'], 1, stdout='', stderr='PERMISSION_DENIED: 403')):
            command_calls = []
            def command(args):
                command_calls.append(args)
                return '[]'
            with self.assertRaisesRegex(RuntimeError, 'could not read prior run-owned resource inventory'):
                cleanup.save_gateway_inventory(
                    bucket='synthetic-bucket', prefix='gcp-lab/runs/12345678',
                    network='retained', project='synthetic-project', work=Path(directory),
                    command=command)
            self.assertEqual(command_calls, [])

    def test_labeled_disk_with_short_generated_name_blocks_completion(self):
        cluster = 'fleet-lab-r12345678901'
        def command(args):
            if 'describe' in args:
                raise subprocess.CalledProcessError(1, args, stderr='NOT_FOUND')
            if 'disks' in args and '--filter' not in args:
                return json.dumps([{'name': 'gke-short-pool-a1b2', 'labels': {
                    'goog-k8s-cluster-name': cluster,
                    'goog-k8s-cluster-location': 'us-central1-a'}}])
            return '[]'
        with self.assertRaisesRegex(RuntimeError, 'disks still exist'):
            cleanup.verify_absent('synthetic-project', cluster, 'us-central1-a', command)

    def test_installer_rejects_corrupt_archive_against_reviewed_checksum(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch('platform.machine', return_value='x86_64'), \
                patch.object(cleanup, 'urlopen', return_value=io.BytesIO(b'corrupt archive')):
            with self.assertRaisesRegex(RuntimeError, 'checksum validation failed'):
                cleanup.install_terraform(Path(directory))
            self.assertFalse((Path(directory) / 'terraform').exists())

    def test_cluster_still_present_prevents_cleanup_success(self):
        with self.assertRaisesRegex(RuntimeError, 'cluster still exists'):
            cleanup.verify_absent('synthetic-project', 'fleet-lab-r12345678901',
                                  'us-central1-a', lambda args: '{}')

    def test_not_found_cluster_still_checks_every_remaining_inventory(self):
        seen = []
        def command(args):
            seen.append(args)
            if 'describe' in args:
                raise subprocess.CalledProcessError(1, args, stderr='NOT_FOUND')
            if 'disks' in args:
                return '[{"name":"gke-fleet-lab-r12345678901-pool-disk"}]'
            return '[]'
        with self.assertRaisesRegex(RuntimeError, 'disks still exist'):
            cleanup.verify_absent('synthetic-project', 'fleet-lab-r12345678901',
                                  'us-central1-a', command)
        self.assertTrue(any('instances' in args for args in seen))
        self.assertTrue(all('--project' in args for args in seen))

    def test_subnet_absence_uses_supported_networks_subnets_group(self):
        cluster = 'fleet-lab-r12345678901'
        seen = []
        def command(args):
            seen.append(args)
            if 'describe' in args:
                raise subprocess.CalledProcessError(1, args, stderr='NOT_FOUND')
            if args[:3] == ['gcloud', 'compute', 'subnetworks']:
                raise subprocess.CalledProcessError(
                    2, args, stderr='Invalid choice: subnetwork')
            return '[]'

        cleanup.verify_absent('synthetic-project', cluster, 'us-central1-a', command)
        subnet_calls = [args for args in seen if 'subnets' in args or 'subnetworks' in args]
        self.assertEqual(len(subnet_calls), 1)
        self.assertEqual(subnet_calls[0][:5],
                         ['gcloud', 'compute', 'networks', 'subnets', 'list'])
        self.assertIn('--project', subnet_calls[0])
        self.assertIn('name~^fleet-lab-r12345678901-subnet$', subnet_calls[0])

    def test_permission_denied_is_not_absence(self):
        def command(args):
            raise subprocess.CalledProcessError(1, args, stderr='PERMISSION_DENIED')
        with self.assertRaises(subprocess.CalledProcessError):
            cleanup.verify_absent('synthetic-project', 'fleet-lab-r12345678901',
                                  'us-central1-a', command)

    def test_recorded_hashed_gateway_rule_prevents_cleanup_success(self):
        link = 'projects/synthetic-project/regions/us-central1/forwardingRules/k8s2-hashed'
        def command(args):
            if 'describe' in args:
                raise subprocess.CalledProcessError(1, args, stderr='NOT_FOUND')
            if 'forwarding-rules' in args and '--filter' not in args:
                return '[{"selfLink":"' + link + '"}]'
            return '[]'
        with self.assertRaisesRegex(RuntimeError, 'forwarding rules still exist'):
            cleanup.verify_absent('synthetic-project', 'fleet-lab-r12345678901',
                                  'us-central1-a', command, {link})
