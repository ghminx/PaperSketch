"""Codex 권한 거부의 분류·전달·재시도 차단 검증."""
import json
from pathlib import Path
import sys
import subprocess
import time
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/paper-sketch/scripts'))
from respond_retrieval import submit_text


class HostPermissionTests(unittest.TestCase):
    def test_permission_response_stops_coordinator_without_waiting_for_timeout(self):
        from respond_retrieval import _permission_failure
        root = Path(__file__).resolve().parents[1]
        with TemporaryDirectory() as temporary:
            work = Path(temporary)
            source = work / 'input.json'
            source.write_text('{"content":"synthetic","visual_intent":"two boxes"}', encoding='utf-8')
            with (work / 'stdout.log').open('wb') as out, (work / 'stderr.log').open('wb') as err:
                process = subprocess.Popen([sys.executable, '-B', str(root / 'skills/paper-sketch/scripts/run.py'),
                    'generate', '--input', str(source), '--dataset-dir', str(root / 'data/diagram'),
                    '--reference-groups', str(root / 'data/diagram/retrieval'), '--output', str(work / 'out'),
                    '--timeout', '30'], stdout=out, stderr=err)
                try:
                    deadline = time.monotonic() + 10
                    requests = []
                    while not requests and process.poll() is None and time.monotonic() < deadline:
                        requests = list((work / 'out').glob('requests/*/request.json'))
                        time.sleep(.02)
                    self.assertEqual(len(requests), 1)
                    request = json.loads(requests[0].read_text(encoding='utf-8'))
                    response = requests[0].with_name('response.json')
                    from bridge import write_json
                    write_json(response, {'id': request['id'], **_permission_failure('codex_exec')})
                    self.assertNotEqual(process.wait(timeout=5), 0)
                    self.assertTrue((work / 'out/failure.json').exists())
                    self.assertFalse((work / 'out/result.json').exists())
                    self.assertEqual(len(list((work / 'out').glob('requests/*/request.json'))), 1)
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()

    def test_permission_failure_is_recorded_once_for_both_hosts(self):
        for phase in ('exec', 'login', 'spawn'):
            with self.subTest(phase=phase), TemporaryDirectory() as temporary:
                path = Path(temporary) / 'request.json'
                path.write_text('{"id":"fixture","kind":"text"}', encoding='utf-8')
                def execute(command, **kwargs):
                    if phase == 'spawn':
                        raise PermissionError('Access is denied')
                    if command[1] == 'login':
                        return SimpleNamespace(returncode=1 if phase == 'login' else 0,
                            stdout=b'ChatGPT', stderr=b'Access is denied (os error 5)' if phase == 'login' else b'')
                    kwargs['stderr'].write(b'unable to open database file\nError: failed to initialize in-process app-server client: Access is denied (os error 5)')
                    return SimpleNamespace(returncode=1)
                with patch('respond_retrieval.shutil.which', return_value='codex'), patch('respond_retrieval.subprocess.run', side_effect=execute) as call:
                    with self.assertRaises((SystemExit, PermissionError)):
                        submit_text(path, model='fixture', timeout=1, prompt='Synthetic fixture only')
                    count = call.call_count
                    raw = path.with_name('response.json').read_bytes()
                    with self.assertRaises(FileExistsError):
                        submit_text(path, model='fixture', timeout=1, prompt='Synthetic fixture only')
                    self.assertEqual(call.call_count, count)
                    self.assertEqual(path.with_name('response.json').read_bytes(), raw)
                response = json.loads(raw)
                self.assertEqual(response['error_type'], 'host_permission_denied')
                self.assertFalse(response['retryable'])
                self.assertNotIn('host', response)

    def test_database_error_alone_is_not_assumed_to_be_permission_denial(self):
        from respond_retrieval import _permission_denied
        self.assertFalse(_permission_denied('unable to open database file'))
        self.assertFalse(_permission_denied('database is locked'))
        self.assertFalse(_permission_denied('WARNING: failed to create PATH aliases: Access is denied (os error 5)'))
        self.assertTrue(_permission_denied('액세스가 거부되었습니다. (os error 5)'))

    def test_successful_answer_with_permission_warning_is_accepted(self):
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / 'request.json'
            path.write_text('{"id":"fixture","kind":"text"}', encoding='utf-8')
            def execute(command, **kwargs):
                if command[1] == 'login':
                    return SimpleNamespace(returncode=0, stdout=b'ChatGPT', stderr=b'')
                Path(command[command.index('-o') + 1]).write_text('OK', encoding='utf-8')
                kwargs['stderr'].write(b'WARNING: failed to clean stale temp dirs: Access is denied (os error 5)')
                kwargs['stdout'].write(b'{"type":"thread.started","thread_id":"fixture"}\n{"type":"turn.completed","usage":{}}\n')
                return SimpleNamespace(returncode=0)
            with patch('respond_retrieval.shutil.which', return_value='codex'), patch('respond_retrieval.subprocess.run', side_effect=execute):
                submit_text(path, model='fixture', timeout=1, prompt='Synthetic fixture only')
            response = json.loads(path.with_name('response.json').read_text(encoding='utf-8'))
            self.assertEqual(response['text'], 'OK')
            self.assertNotIn('error_type', response)


if __name__ == '__main__':
    unittest.main()
