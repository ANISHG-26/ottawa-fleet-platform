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
