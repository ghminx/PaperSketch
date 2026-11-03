import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/paper-sketch/scripts'))
from bridge import FileBridge, write_json
from respond_text import text_prompt
from respond_retrieval import submit_text


class TextHostTests(unittest.TestCase):
    def test_ordered_conversation_and_images_preserve_explicit_inputs_only(self):
        with TemporaryDirectory() as temp:
            image = Path(temp) / 'input.image'
            image.write_bytes(b'image fixture')
            turns = [{'role': 'user', 'content': [
                {'type': 'text', 'text': 'Earlier requirement'},
                {'type': 'image', 'path': str(image), 'media_type': 'image/jpeg'},
                {'type': 'text', 'text': 'Current requirement'}]},
                {'role': 'model', 'content': [{'type': 'text', 'text': 'Recorded critique'}]},
                {'role': 'user', 'content': [{'type': 'text', 'text': 'YES or NO'}]}]
            prompt, images = text_prompt({'kind': 'text', 'config': {'system_instruction': 'UPSTREAM'},
                                         'turns': turns, 'unrelated_saved_description': 'HIDDEN_RENDER_TEXT'})
            restored = json.loads(prompt.split('ORDERED CONVERSATION JSON:\n')[1])
            self.assertEqual([t['role'] for t in restored], ['user', 'model', 'user'])
            self.assertEqual(restored[0]['content'][1]['attachment'], 1)
            self.assertEqual(restored[1:], turns[1:])
            self.assertEqual(images, [image])
            self.assertNotIn('HIDDEN_RENDER_TEXT', prompt)
            with self.assertRaisesRegex(ValueError, 'text request'):
                text_prompt({'kind': 'image'})

    def test_executor_fresh_context_and_failure_rejection(self):
        for mode in ('success', 'tool', 'timeout', 'empty', 'review_empty'):
            with self.subTest(mode=mode), TemporaryDirectory() as temp:
                path = Path(temp) / 'request.json'
                request = {'id': 'REQUEST', 'kind': 'text'}
                if mode == 'review_empty': request['review_validation'] = {'stage': 'critique', 'number': 1, 'final': True}
                write_json(path, request)

                def run(command, **kwargs):
                    if command[1] == 'login':
                        return SimpleNamespace(returncode=0, stdout=b'ChatGPT', stderr=b'')
                    self.assertIn('--ephemeral', command)
                    self.assertNotIn('resume', command)
                    self.assertIn('project_doc_max_bytes=0', command)
                    self.assertIn('memories.use_memories=false', command)
                    self.assertNotIn('OPENAI_API_KEY', kwargs['env'])
                    self.assertEqual(kwargs['input'], b'ONLY THIS REQUEST')
                    if mode == 'timeout':
                        raise subprocess.TimeoutExpired(command, 1)
                    answer = Path(command[command.index('-o')+1])
                    answer.write_text('' if mode in ('empty', 'review_empty') else 'YES', encoding='utf-8')
                    events = [{'type': 'thread.started', 'thread_id': 'fresh-thread'},
                              {'type': 'turn.completed', 'usage': {'input_tokens': 10}}]
                    if mode == 'tool':
                        events.append({'type': 'item.completed', 'item': {'type': 'command_execution'}})
                    kwargs['stdout'].write(('\n'.join(json.dumps(e) for e in events)).encode())
                    return SimpleNamespace(returncode=0)

                with patch('respond_retrieval.shutil.which', return_value='codex'), \
                     patch('respond_retrieval.subprocess.run', side_effect=run):
                    if mode in ('success', 'review_empty'):
                        submit_text(path, model='test-model', timeout=1, prompt='ONLY THIS REQUEST')
                    else:
                        with self.assertRaises(SystemExit):
                            submit_text(path, model='test-model', timeout=1, prompt='ONLY THIS REQUEST')
                    with self.assertRaises(FileExistsError):
                        submit_text(path, model='test-model', timeout=1, prompt='ONLY THIS REQUEST')
                response = json.loads(path.with_name('response.json').read_text(encoding='utf-8'))
                metadata = json.loads((path.parent/'codex-host/metadata.json').read_text(encoding='utf-8'))
                self.assertEqual(metadata['request_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(metadata['requested_model'], 'test-model')
                if mode in ('success', 'review_empty'):
                    self.assertEqual(response['host']['request_sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                    self.assertEqual(response['host']['response_sha256'], hashlib.sha256(
                        b'' if mode == 'review_empty' else b'YES').hexdigest())
                else:
                    self.assertIn('error', response)


class IndependentBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_manual_or_stale_text_response_rejected(self):
        import asyncio
        for mode in ('manual', 'stale', 'valid'):
            with self.subTest(mode=mode), TemporaryDirectory() as temp:
                bridge = FileBridge(Path(temp), timeout=2, independent_text=True)
                task = asyncio.create_task(bridge.call('host', [{'type': 'text', 'text': 'Critique'}], {}))
                await asyncio.sleep(.02)
                path = next(Path(temp).glob('*/request.json'))
                request = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(request['required_text_host'], 'independent-codex')
                response = {'id': request['id'], 'text': 'OK'}
                if mode != 'manual':
                    response['host'] = {'type': 'independent-codex',
                        'request_sha256': 'stale' if mode == 'stale' else hashlib.sha256(path.read_bytes()).hexdigest(),
                        'response_sha256': hashlib.sha256(b'OK').hexdigest()}
                write_json(path.with_name('response.json'), response)
                if mode == 'valid':
                    self.assertEqual(await task, ['OK'])
                else:
                    with self.assertRaisesRegex(ValueError, 'host evidence'):
                        await task
