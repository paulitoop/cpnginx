import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('lab_cli', Path(__file__).resolve().parents[1]/'cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class InventoryTests(unittest.TestCase):
    def test_one_and_two_nodes_have_no_balancer_or_layers(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(cli, 'STATE', Path(directory)):
            cli.save(cli.STATE/'approle.json', {'role_id': 'example-role', 'secret_id': 'example-not-a-real-secret'})
            for nodes in [1, 2]:
                cli.inventory(nodes)
                data = cli.load(cli.STATE/'inventory.json')
                hosts = data['all']['children']['cpnginx']['hosts']
                self.assertEqual(len(hosts), nodes)
                self.assertEqual([h['ansible_port'] for h in hosts.values()], list(range(2221, 2221+nodes)))
                self.assertNotIn('layers', json.dumps(data))
                self.assertNotIn('balancer', json.dumps(data))
                self.assertEqual((cli.STATE/'inventory.json').stat().st_mode & 0o777, 0o600)

    def test_api_error_does_not_disclose_request_body_or_token(self):
        from urllib.error import HTTPError
        with patch.object(cli.urllib.request, 'urlopen', side_effect=HTTPError('http://localhost', 403, 'forbidden', {}, None)):
            with self.assertRaises(cli.LabError) as result:
                cli.api('test', {'pin': 'private-value'}, token='private-token')
            self.assertNotIn('private', str(result.exception))
            self.assertIn('HTTP 403', str(result.exception))


class RejectionEvidenceTests(unittest.TestCase):
    def test_rotated_log_is_not_accepted_as_fresh_evidence(self):
        self.assertEqual(cli.log_delta('old\n', 'old\nnew\n'), 'new\n')
        with self.assertRaises(cli.LabError):
            cli.log_delta('old\n', 'replacement\n')

    def test_unrelated_tls_failure_is_not_a_successful_negative_test(self):
        from types import SimpleNamespace
        with patch.object(cli, 'require_prepared'), patch.object(cli, 'load', return_value={'nodes': 1}), \
             patch.object(cli, 'partner_log', side_effect=['', 'status=200 request="GET /tls"', '', 'handshake failed']), \
             patch.object(cli, 'probe', side_effect=[SimpleNamespace(returncode=0, stdout=''), SimpleNamespace(returncode=4, stdout='')]):
            with self.assertRaisesRegex(cli.LabError, 'No confirmed rejection'):
                cli.check('before')


class LaboratoryRngTests(unittest.TestCase):
    def test_fresh_pools_have_valid_records_and_no_fixed_gamma(self):
        import struct
        import zlib
        spec = importlib.util.spec_from_file_location('lab_rng', Path(__file__).resolve().parents[1]/'docker/init-rng.py')
        rng = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rng)
        first, second = rng.fresh_pool(4), rng.fresh_pool(4)
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 4*36)
        for offset in range(0, len(first), 36):
            record = first[offset:offset+36]
            self.assertEqual(record[32:], struct.pack('<I', zlib.crc32(record[:32])))


if __name__ == '__main__':
    unittest.main()
