"""Diagram 실행기 시작과 실제 모델 호출의 경계 검증."""
import asyncio
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]

BOOTSTRAP = r'''
import json, os, runpy, sys
audit_file, script = sys.argv[1:3]
def guard(event, args):
    # 별도 프로세스의 고정 비동기 사전 검사만 허용
    if event == 'subprocess.Popen' and '--papersketch-asyncio-probe' in args[1]:
        return
    # Windows asyncio의 로컬 socketpair 통신만 허용
    if event == 'socket.connect' and isinstance(args[1], tuple) and args[1][0] in ('127.0.0.1', '::1'):
        return
    if event in ('socket.connect', 'socket.getaddrinfo', 'subprocess.Popen', 'os.system'):
        with open(audit_file, 'a', encoding='utf-8') as log:
            log.write(event + '\n')
        raise PermissionError('External execution blocked by local-launch test: ' + event)
sys.addaudithook(guard)
sys.argv = sys.argv[2:]
sys.path.insert(0, os.path.dirname(script))
runpy.run_path(script, run_name='__main__')
'''


class LocalLaunchTests(unittest.IsolatedAsyncioTestCase):
    async def test_generate_emits_local_request_without_network_or_model_process(self):
        """실제 auto 시작 경로가 외부 호출 없이 요청 파일에서 대기함을 확인."""
        with TemporaryDirectory() as temporary:
            work = Path(temporary)
            source = work / 'input.json'
            source.write_text(json.dumps({'content': 'SYNTHETIC input -> encoder -> output.',
                                          'visual_intent': 'Synthetic architecture test.'}), encoding='utf-8')
            audit = work / 'blocked-events.log'
            env = os.environ.copy()
            env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
            with (work / 'stderr.log').open('wb') as errors:
                process = await asyncio.create_subprocess_exec(sys.executable, '-B', '-c', BOOTSTRAP,
                    str(audit), str(ROOT / 'skills/paper-sketch/scripts/run.py'), 'generate',
                    '--input', str(source), '--dataset-dir', str(ROOT / 'data/diagram'),
                    '--reference-groups', str(ROOT / 'data/diagram/retrieval'),
                    '--output', str(work / 'out'), '--retrieval', 'auto', '--timeout', '60',
                    cwd=work, env=env, stdout=asyncio.subprocess.PIPE, stderr=errors)
                try:
                    request_path = None
                    while raw := await asyncio.wait_for(process.stdout.readline(), 30):
                        line = raw.decode('utf-8').strip()
                        if line.startswith('PAPER_SKETCH_REQUEST '):
                            request_path = Path(line.removeprefix('PAPER_SKETCH_REQUEST '))
                            break
                    self.assertIsNotNone(request_path, (work / 'stderr.log').read_text(encoding='utf-8'))
                    request = json.loads(request_path.read_text(encoding='utf-8'))
                    self.assertEqual(request['kind'], 'text')
                    self.assertTrue(request_path.is_relative_to(work / 'out'))
                    text = json.dumps(request, ensure_ascii=False)
                    self.assertIn('SYNTHETIC input', text)
                    group = json.loads((ROOT / 'data/diagram/retrieval/group-01.json').read_text(encoding='utf-8'))
                    for row in group:
                        self.assertIn(row['id'], text)
                    self.assertFalse(request_path.with_name('response.json').exists())
                    self.assertIsNone(process.returncode)
                    self.assertFalse(audit.exists(), audit.read_text() if audit.exists() else '')
                finally:
                    if process.returncode is None:
                        process.kill()
                    await process.wait()


if __name__ == '__main__':
    unittest.main()
