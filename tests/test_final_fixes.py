"""코드 clip 보정·검색 그룹 재현·host 사전 실패 응답의 회귀 검증."""
import asyncio
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
from state import load_result
from bridge import FileBridge, write_json
from plot_code import prepare_plot_code
from prepare_reference_groups import prepare_groups
from respond_retrieval import submit_text
from respond_text import text_prompt

CLIP_CODE = '''import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
fig, ax = plt.subplots()
ax.set(xlim=(0, 1), ylim=(0, 1))
bar = ax.bar([.5], [.8], width=.3)[0]
strokes = LineCollection([[(0, .1), (1, .9)]])
strokes.set_clip_path(bar)
ax.add_collection(strokes)'''


class ClipFixTests(unittest.TestCase):
    def test_fix_preserves_bar_clip_and_is_idempotent(self):
        import matplotlib
        matplotlib.use('Agg', force=True)
        import matplotlib.pyplot as plt
        import numpy as np
        original = {}
        exec(CLIP_CODE, original)
        original['fig'].canvas.draw()
        self.assertFalse(np.allclose(original['strokes'].get_clip_box().extents,
                                     original['bar'].get_window_extent().extents))
        code, repairs = prepare_plot_code('```python\n'+CLIP_CODE+'\n```')
        fixed = {}
        exec(code, fixed)
        fixed['fig'].canvas.draw()
        self.assertTrue(np.allclose(fixed['strokes'].get_clip_box().extents,
                                    fixed['bar'].get_window_extent().extents))
        self.assertEqual(len(repairs), 1)
        self.assertEqual(prepare_plot_code(code), (code, []))
        self.assertEqual(fixed['bar'].get_height(), .8)
        plt.close('all')

    def test_other_code_and_nonadjacent_operations_unchanged(self):
        for code in [
            'strokes.set_clip_path(bar)\nax.add_collection(other)',
            'strokes.set_clip_path(bar)\nvalue = 1\nax.add_collection(strokes)',
            'strokes.set_clip_path(make_bar())\nax.add_collection(strokes)',
            'ax.add_collection(strokes)\nstrokes.set_clip_path(bar)',
            'strokes.set_clip_path(bar); ax.add_collection(strokes)',
            'value = 1; strokes.set_clip_path(bar)\nax.add_collection(strokes)',
            'strokes.set_clip_path(bar)\nax.add_collection(strokes); value = 1',
            'invalid syntax !!!',
        ]:
            self.assertEqual(prepare_plot_code(code), (code, []))

    def test_nested_multiline_calls_and_unicode_comments_preserved(self):
        code = ('for strokes in items:\n    # 막대 내부 제한\n'
                '    strokes.set_clip_path(\n        bar\n    )\n'
                '    ax.add_collection(\n        strokes, autolim=False\n    )')
        output, repairs = prepare_plot_code(code)
        compile(output, '<fixture>', 'exec')
        self.assertEqual(len(repairs), 1)
        self.assertIn('# 막대 내부 제한', output)
        self.assertLess(output.index('ax.add_collection'), output.index('strokes.set_clip_path'))

    def test_repair_changes_only_target_calls_without_historical_artifacts(self):
        original = CLIP_CODE
        code, repairs = prepare_plot_code(original)
        self.assertEqual(len(repairs), 1)
        self.assertEqual(code, original.replace('strokes.set_clip_path(bar)\nax.add_collection(strokes)',
                                               'ax.add_collection(strokes)\nstrokes.set_clip_path(bar)'))

    def test_windows_line_endings_remain_executable_and_export_exactly(self):
        from state import _plot_code
        source = CLIP_CODE.replace('\n', '\r\n')
        code, repairs = prepare_plot_code(source)
        compile(code, '<windows fixture>', 'exec')
        self.assertEqual(len(repairs), 1)
        self.assertEqual(_plot_code({'desc_code': source, 'desc_executed_code': code}, 'desc'), code.encode())


class GroupPreparationTests(unittest.TestCase):
    def test_current_groups_reproduced_from_full_data_without_changes(self):
        dataset = ROOT / 'data/diagram'
        before = hashlib.sha256((dataset / 'ref.json').read_bytes()).hexdigest()
        old_root = dataset / 'retrieval'
        old = json.loads((old_root / 'manifest.json').read_text(encoding='utf-8'))
        with TemporaryDirectory() as temporary:
            output = Path(temporary) / 'groups'
            manifest = prepare_groups(dataset, output)
            self.assertEqual([g['records'] for g in manifest['groups']], [53, 51, 58, 38])
            self.assertEqual(manifest['source_ref_sha256'], old['source_ref_sha256'])
            for actual, expected in zip(manifest['groups'], old['groups']):
                self.assertEqual(actual['text_sha256'], expected['text_sha256'])
                self.assertEqual(actual['ids'], expected['ids'])
                self.assertEqual((output / actual['text_file']).read_text(encoding='utf-8'),
                                 (old_root / expected['text_file']).read_text(encoding='utf-8'))
                self.assertEqual(json.loads((output / actual['json_file']).read_text(encoding='utf-8')),
                                 json.loads((old_root / expected['json_file']).read_text(encoding='utf-8')))
            with self.assertRaises(FileExistsError):
                prepare_groups(dataset, output)
            self.assertEqual(len(list(output.iterdir())), 9)
        self.assertEqual(hashlib.sha256((dataset / 'ref.json').read_bytes()).hexdigest(), before)

    def test_invalid_source_fails_before_output_publication(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'source'
            source.mkdir()
            for rows in [[], [{'id': f'r{i}', 'content': 'x' * 800001, 'visual_intent': 'caption'} for i in range(200)]]:
                write_json(source / 'ref.json', rows)
                output = root / 'groups'
                with self.assertRaises(ValueError):
                    prepare_groups(source, output)
                self.assertFalse(output.exists())


class HostPreflightTests(unittest.TestCase):
    def test_both_cli_entrypoints_write_preflight_failure(self):
        import respond_text
        import respond_retrieval
        for module in (respond_text, respond_retrieval):
            with self.subTest(module=module.__name__), TemporaryDirectory() as temporary:
                path = Path(temporary) / 'request.json'
                write_json(path, {'id': 'request', 'kind': 'text',
                    'config': {'system_instruction': 'Return selected_diagrams'},
                    'turns': [{'role': 'user', 'content': [{'type': 'text', 'text': 'fixture'}]}]})
                with patch('sys.argv', [module.__name__, str(path), '--model', 'unused']), \
                     patch('respond_retrieval.shutil.which', return_value=None):
                    with self.assertRaisesRegex(RuntimeError, 'Codex CLI is required'):
                        module.main()
                response = json.loads(path.with_name('response.json').read_text(encoding='utf-8'))
                self.assertEqual(response['error_type'], 'host_failure')

    def test_cli_login_timeout_and_spawn_failures_write_error_once(self):
        for mode in ('missing', 'login', 'login_timeout', 'spawn'):
            with self.subTest(mode=mode), TemporaryDirectory() as temporary:
                path = Path(temporary) / 'request.json'
                write_json(path, {'id': 'request', 'kind': 'text'})
                side_effect = (subprocess.TimeoutExpired('login', 1) if mode == 'login_timeout' else
                               OSError('local process failed') if mode == 'spawn' else
                               SimpleNamespace(returncode=1, stdout=b'', stderr=b'Not logged in'))
                with patch('respond_retrieval.shutil.which', return_value=None if mode == 'missing' else 'codex'), \
                     patch('respond_retrieval.subprocess.run', side_effect=side_effect if isinstance(side_effect, Exception) else None,
                           return_value=side_effect):
                    with self.assertRaises((RuntimeError, OSError, subprocess.TimeoutExpired)):
                        submit_text(path, model='unused', timeout=1, prompt='fixture')
                raw = path.with_name('response.json').read_bytes()
                response = json.loads(raw)
                self.assertEqual(response['id'], 'request')
                self.assertEqual(response['error_type'], 'host_failure')
                with self.assertRaises(FileExistsError):
                    submit_text(path, model='unused', timeout=1, prompt='fixture')
                self.assertEqual(path.with_name('response.json').read_bytes(), raw)

    def test_prompt_and_missing_image_fail_before_external_execution(self):
        for part in [{'type': 'text', 'text': 'x' * 1048576},
                     {'type': 'image', 'path': str(ROOT / 'missing-image.png'), 'media_type': 'image/png'}]:
            with self.subTest(part=part['type']), TemporaryDirectory() as temporary:
                path = Path(temporary) / 'request.json'
                write_json(path, {'id': 'request', 'kind': 'text', 'config': {},
                                 'turns': [{'role': 'user', 'content': [part]}]})
                with patch('respond_retrieval.subprocess.run') as execute:
                    with self.assertRaises(ValueError):
                        submit_text(path, model='unused', timeout=1, prompt_builder=text_prompt)
                    execute.assert_not_called()
                self.assertIn('error', json.loads(path.with_name('response.json').read_text(encoding='utf-8')))


class HostBridgeFailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_preflight_failure_unblocks_waiting_bridge(self):
        with TemporaryDirectory() as temporary:
            bridge = FileBridge(Path(temporary), timeout=3)
            task = asyncio.create_task(bridge.call('fixture', [{'type': 'text', 'text': 'fixture'}], {}))
            while not bridge.request_paths:
                await asyncio.sleep(.01)
            with patch('respond_retrieval.shutil.which', return_value=None):
                with self.assertRaises(RuntimeError):
                    submit_text(bridge.request_paths[0], model='unused', timeout=1, prompt='fixture')
            with self.assertRaisesRegex(RuntimeError, 'Codex CLI is required'):
                await asyncio.wait_for(task, 1)


if __name__ == '__main__':
    unittest.main()
