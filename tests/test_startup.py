"""비동기 초기화 timeout·진단·기존 실행 진입 차단 검증."""
from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/paper-sketch/scripts'))
from startup_check import check_asyncio, require_asyncio


class StartupTests(unittest.TestCase):
    def test_pass_checks_only_local_asyncio_and_returns_evidence(self):
        reply = subprocess.CompletedProcess([], 0, b'ASYNCIO_PROBE_STARTED\nASYNCIO_PROBE_OK\n', b'')
        with patch('startup_check.subprocess.run', return_value=reply) as call:
            result = check_asyncio()
        self.assertEqual(result['status'], 'passed')
        command = call.call_args.args[0]
        self.assertEqual(command[0], sys.executable)
        self.assertIn('asyncio.run(asyncio.sleep(0))', command[5])
        self.assertEqual(call.call_args.kwargs['timeout'], 5)
        self.assertEqual(result['model_calls'], 0)

    def test_socketpair_timeout_is_distinguished_from_unknown_timeout(self):
        for stack, expected in [(b'File socket.py in accept\nFile socket.py in socketpair', 'loopback_initialization_stalled'),
                                (b'File other.py in something', 'asyncio_initialization_timeout')]:
            with self.subTest(expected=expected), patch('startup_check.subprocess.run',
                side_effect=subprocess.TimeoutExpired([], 5, output=b'ASYNCIO_PROBE_STARTED\n', stderr=stack)):
                result = check_asyncio()
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['diagnosis'], expected)
                self.assertEqual(result['stderr'], stack.decode())

    def test_launch_failure_and_missing_start_marker_do_not_invent_socket_cause(self):
        for error, expected in [(PermissionError('blocked'), 'probe_launch_failed'),
                                (subprocess.TimeoutExpired([], 5), 'python_startup_timeout')]:
            with self.subTest(expected=expected), patch('startup_check.subprocess.run', side_effect=error):
                self.assertEqual(check_asyncio()['diagnosis'], expected)

    def test_error_exit_and_output_are_not_silent_or_success(self):
        reply = subprocess.CompletedProcess([], 1, b'', b'failure details')
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch('startup_check.subprocess.run', return_value=reply), redirect_stdout(stdout), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                require_asyncio()
        self.assertEqual(error.exception.code, 2)
        self.assertIn('"status": "checking"', stdout.getvalue())
        self.assertIn('failure details', stdout.getvalue())
        self.assertIn('No automatic retry', stderr.getvalue())


if __name__ == '__main__':
    unittest.main()
