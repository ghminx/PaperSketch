import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/paper-sketch/scripts'
sys.path.insert(0, str(SCRIPTS))
from bridge import FileBridge, write_json
from state import load_result, save_result


class ImageRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def exchange(self, bridge, replies):
        """실제 파일 bridge의 이미지 요청을 모의 성공·실패로 처리."""
        task = asyncio.create_task(bridge.call('image-host', [{'type': 'text', 'text': 'ORIGINAL PROMPT'}],
            {'response_modalities': ['IMAGE']}, max_attempts=len(replies), retry_delay=0))
        requests = []
        try:
            for reply in replies:
                for _ in range(100):
                    pending = [p for p in bridge.directory.glob('*/request.json')
                               if not p.with_name('response.json').exists()]
                    if pending: break
                    await asyncio.sleep(.01)
                self.assertEqual(len(pending), 1)
                path = pending[0]
                request = json.loads(path.read_text(encoding='utf-8'))
                requests.append(request)
                write_json(path.with_name('response.json'), {'id': request['id'], **reply})
            return await task, requests
        finally:
            if not task.done():
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass

    async def test_transient_then_success_uses_new_id_and_same_prompt(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            image = root / 'image.png'
            Image.new('RGB', (32,18), 'blue').save(image)
            bridge = FileBridge(root / 'requests', timeout=1)
            result, requests = await self.exchange(bridge, [
                {'error': 'Service unavailable', 'error_type': 'transient'}, {'image_path': str(image)}])
            self.assertEqual(base64.b64decode(result[0]), image.read_bytes())
            self.assertNotEqual(requests[0]['id'], requests[1]['id'])
            self.assertEqual(requests[0]['turns'], requests[1]['turns'])
            self.assertEqual(requests[0]['image_attempt']['call_id'], requests[1]['image_attempt']['call_id'])
            self.assertEqual(bridge.image_calls[0]['status'], 'succeeded')
            self.assertEqual(len(bridge.image_calls[0]['attempts']), 2)

    async def test_exhausted_and_nonretryable_errors_return_upstream_failure(self):
        for category in ('transient', 'quota', 'refused', 'unknown'):
            with self.subTest(category=category), TemporaryDirectory() as temp:
                bridge = FileBridge(Path(temp), timeout=1)
                count = 2 if category == 'transient' else 1
                result, requests = await self.exchange(bridge, [{'error': 'Failure', 'error_type': category}] * count)
                self.assertEqual(result, ['Error'])
                self.assertEqual(len(bridge.image_calls[0]['attempts']), count)
                self.assertEqual(bridge.image_calls[0]['status'], 'failed')

    async def test_invalid_input_aborts_and_corrupt_image_falls_back(self):
        with TemporaryDirectory() as temp:
            bridge = FileBridge(Path(temp) / 'invalid', timeout=1)
            with self.assertRaisesRegex(RuntimeError, 'Bad request'):
                await self.exchange(bridge, [{'error': 'Bad request', 'error_type': 'invalid_input'}])
            path = Path(temp) / 'bad.png'
            path.write_text('not an image')
            bridge = FileBridge(Path(temp) / 'corrupt', timeout=1)
            result, _ = await self.exchange(bridge, [{'image_path': str(path)}])
            self.assertEqual(result, ['Error'])
            self.assertEqual(bridge.image_calls[0]['attempts'][0]['error_type'], 'invalid_image')

    async def test_quota_blocks_later_image_calls_in_the_same_run(self):
        with TemporaryDirectory() as temp:
            bridge = FileBridge(Path(temp), timeout=1)
            await self.exchange(bridge, [{'error': 'Quota', 'error_type': 'quota'}])
            result = await bridge.call('host', [], {'response_modalities': ['IMAGE']})
            self.assertEqual(result, ['Error'])
            self.assertEqual(len(list(Path(temp).glob('*/request.json'))), 1)
            self.assertEqual(bridge.image_calls[-1]['blocked_by']['error_type'], 'quota')
            self.assertEqual(bridge.image_calls[-1]['attempts'], [])

    async def test_timeout_does_not_retry_and_rejects_late_submission(self):
        with TemporaryDirectory() as temp:
            bridge = FileBridge(Path(temp), timeout=0)
            result = await bridge.call('host', [], {'response_modalities': ['IMAGE']}, max_attempts=5, retry_delay=0)
            self.assertEqual(result, ['Error'])
            self.assertEqual(len(bridge.image_calls[0]['attempts']), 1)
            self.assertEqual(bridge.image_calls[0]['attempts'][0]['error_type'], 'timeout')
            path = next(Path(temp).glob('*/request.json'))
            process = await asyncio.create_subprocess_exec(sys.executable, '-B', str(SCRIPTS/'respond.py'),
                str(path), '--error', 'late', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, errors = await process.communicate()
            self.assertNotEqual(process.returncode, 0)
            self.assertIn(b'already closed', errors)
            self.assertFalse(path.with_name('response.json').exists())

    async def cli(self, root, action, image_replies):
        """정식 CLI를 모의 host로 구동하고 실제 저장 결과 확인."""
        output = root / 'out'
        base = [sys.executable, '-B', str(SCRIPTS/'run.py'), action, '--output', str(output),
                '--dataset-dir', str(root), '--timeout', '10']
        if action == 'generate':
            write_json(root/'input.json', {'content': 'SOURCE', 'visual_intent': 'CAPTION'})
            base += ['--input', str(root/'input.json'), '--retrieval', 'none', '--critic-rounds', '0']
            texts = ['Planner description', 'Stylist description',
                     '{"critic_suggestions":"No changes needed.","revised_description":"No changes needed."}']
        else:
            buffer = io.BytesIO()
            Image.new('RGB', (32,18), 'blue').save(buffer, format='JPEG')
            field = 'target_diagram_desc0_base64_jpg'
            data = {'content': 'SOURCE', 'visual_intent': 'CAPTION', field: base64.b64encode(buffer.getvalue()).decode(),
                    'target_diagram_desc0': 'Original blue figure', 'eval_image_field': field,
                    'chat_history': [{'role': 'assistant', 'content': 'Generated.'}]}
            await save_result(root/'prior', data)
            (root/'feedback.txt').write_text('Add arrow', encoding='utf-8')
            base += ['--prior', str(root/'prior/result.json'), '--feedback-file', str(root/'feedback.txt')]
            texts = ['{"context_diagram1":"blue", "context_user_turn1":"arrow"}',
                     '{"critique_latest_turn":"Missing arrow","critique_source_content":"Missing arrow","critique_presentation":"Clear"}', 'YES',
                     '{"critic_suggestions":"Add arrow", "revised_description":"New arrow description"}']
        process = await asyncio.create_subprocess_exec(*base, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        text_index = image_index = 0
        lines = []
        try:
            while raw := await asyncio.wait_for(process.stdout.readline(), timeout=15):
                line = raw.decode('utf-8').strip()
                lines.append(line)
                if not line.startswith('PAPER_SKETCH_REQUEST '): continue
                path = Path(line.removeprefix('PAPER_SKETCH_REQUEST '))
                request = json.loads(path.read_text(encoding='utf-8'))
                response = {'id': request['id']}
                if request['kind'] == 'text':
                    text = texts[text_index]; text_index += 1
                    response.update(text=text, host={'type': 'independent-codex',
                        'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'response_sha256': hashlib.sha256(text.encode()).hexdigest()})
                else:
                    response.update(image_replies[image_index]); image_index += 1
                write_json(path.with_name('response.json'), response)
            _, stderr = await process.communicate()
            return process.returncode, output, '\n'.join(lines), stderr.decode('utf-8')
        finally:
            if process.returncode is None:
                process.kill(); await process.wait()

    async def test_refine_quota_failure_preserves_previous_and_attempt(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            code, output, stdout, stderr = await self.cli(root, 'refine', [{'error': 'quota reached', 'error_type': 'quota'}])
            self.assertEqual(code, 0, stderr)
            self.assertIn('completed_with_image_failures', stdout)
            self.assertEqual((output/'final.jpg').read_bytes(), (root/'prior/final.jpg').read_bytes())
            restored = await load_result(output/'result.json')
            self.assertEqual(restored['chat_history'][1]['content'], 'Add arrow')
            self.assertEqual(restored['target_diagram_critic_desc1-0'], 'New arrow description')
            self.assertTrue(restored['target_diagram_critic_desc1-0_gen_failed'])
            self.assertEqual(restored['image_generation_history'][-1]['attempts'][0]['error_type'], 'quota')
            self.assertEqual((output/'description.txt').read_text(), 'Original blue figure')

    async def test_initial_render_failures_have_explicit_failure_or_valid_fallback(self):
        for modes in [('fail','fail'), ('ok','fail'), ('fail','ok')]:
            with self.subTest(modes=modes), TemporaryDirectory() as temp:
                root = Path(temp)
                image = root/'fixture.png'
                Image.new('RGB', (32,18), 'blue').save(image)
                replies = [{'image_path': str(image)} if mode == 'ok' else {'error': 'unavailable', 'error_type': 'unknown'}
                           for mode in modes]
                code, output, stdout, stderr = await self.cli(root, 'generate', replies)
                if modes == ('fail','fail'):
                    self.assertNotEqual(code, 0)
                    self.assertTrue((output/'failure.json').exists())
                    self.assertFalse((output/'result.json').exists())
                    self.assertFalse((output/'final.jpg').exists())
                    failed = json.loads((output/'failed_record.json').read_text(encoding='utf-8'))
                    self.assertEqual(failed['target_diagram_desc0'], 'Planner description')
                    self.assertEqual(failed['target_diagram_stylist_desc0'], 'Stylist description')
                    with self.assertRaisesRegex(ValueError, 'failed run'):
                        await load_result(output/'failed_record.json')
                else:
                    self.assertEqual(code, 0, stderr)
                    result = await load_result(output/'result.json')
                    selected = 'target_diagram_desc0_base64_jpg' if modes[0]=='ok' else 'target_diagram_stylist_desc0_base64_jpg'
                    self.assertEqual(result['eval_image_field'], selected)
                    self.assertIn('completed_with_image_failures', stdout)

    async def test_fatal_refine_failure_saves_incomplete_record_not_success(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            code, output, stdout, stderr = await self.cli(root, 'refine', [{'error': 'invalid options', 'error_type': 'invalid_input'}])
            self.assertNotEqual(code, 0)
            self.assertNotIn('completed_with_image_failures', stdout)
            self.assertFalse((output/'result.json').exists())
            self.assertTrue((root/'prior/final.jpg').exists())
            failure = json.loads((output/'failure.json').read_text(encoding='utf-8'))
            self.assertEqual(failure['status'], 'failed')
            failed = json.loads((output/'failed_record.json').read_text(encoding='utf-8'))
            self.assertEqual(failed['chat_history'][-1]['content'], 'Add arrow')
            self.assertEqual(failed['target_diagram_critic_desc1-0'], 'New arrow description')
