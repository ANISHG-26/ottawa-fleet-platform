import io
import json
import unittest
from scripts.ci_log_masks import emit_masks, private_masks


class CiLogMaskTests(unittest.TestCase):
    def test_masks_nested_private_fields_and_federation_project_number(self):
        masks = private_masks(json.dumps({'project_id': 'private-project', 'nested': [
            {'database_password': 'secret-password'}], 'flag': True, 'node_count': 1}),
            'projects/123456789012/locations/global/workloadIdentityPools/pool/providers/provider')
        self.assertEqual(masks, ['123456789012', 'private-project', 'secret-password'])

    def test_newlines_and_percent_cannot_inject_workflow_commands(self):
        output = io.StringIO()
        emit_masks(json.dumps({'value': 'value%\r\n::warning::injected'}), 'projects/123456789012/locations/global/workloadIdentityPools/pool/providers/provider', output)
        self.assertEqual(output.getvalue(), '::add-mask::123456789012\n::add-mask::value%25%0D%0A::warning::injected\n')

    def test_invalid_json_fails_before_any_partial_mask_output(self):
        output = io.StringIO()
        with self.assertRaises(ValueError):
            emit_masks('{invalid', '', output)
        self.assertEqual(output.getvalue(), '')

    def test_malformed_provider_fails_before_any_mask_output(self):
        for provider in ('', 'projects/not-a-number/locations/global/workloadIdentityPools/pool/providers/provider',
                         'projects/123456789012/locations/global/providers/provider'):
            output = io.StringIO()
            with self.subTest(provider=provider), self.assertRaises(ValueError):
                emit_masks('{"project_id":"private-project"}', provider, output)
            self.assertEqual(output.getvalue(), '')
