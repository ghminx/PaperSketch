"""원본 Plot 흐름·실제 Matplotlib 실행·저장 및 실패 경로 검증."""
import asyncio
import ast
import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/paper-sketch/scripts'
VENDOR = ROOT / 'skills/paper-sketch/assets/paperbanana_plot'
sys.path.insert(0, str(SCRIPTS))
from bridge import write_json
from state import load_result, summarize_result


def system_prompt(agent):
    tree = ast.parse((VENDOR / f'agents/{agent}_agent.py').read_text(encoding='utf-8'))
    key = f'PLOT_{agent.upper()}_AGENT_SYSTEM_PROMPT'
    return next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == key for target in node.targets))


CODE = """import matplotlib.pyplot as plt
labels = ['A', 'B', 'C']
values = [10, 15, 12]
fig, ax = plt.subplots(figsize=(5, 3))
ax.bar(labels, values, color=['#5684a6', '#6f9d88', '#c69768'])
ax.set_ylabel('Value')
fig.tight_layout()
"""


class PlotTests(unittest.IsolatedAsyncioTestCase):
    async def run_fixture(self, root, *, mode='auto', scenario='clean', rounds=1, plot_timeout=30):
        output = root / 'out'
        input_path = root / 'input.json'
        write_json(input_path, {'content': {'A': 10, 'B': 15, 'C': 12},
                               'visual_intent': 'Bar chart with one bar for each category; preserve all values.'})
        command = [sys.executable, '-B', str(SCRIPTS / 'run.py'), 'generate', '--task', 'plot',
                   '--input', str(input_path), '--dataset-dir', str(ROOT / 'data/plot'),
                   '--output', str(output), '--retrieval', mode, '--critic-rounds', str(rounds),
                   '--plot-timeout', str(plot_timeout), '--timeout', '5']
        process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)
        requests, lines = [], []
        visualizers, critics = 0, 0
        try:
            while raw := await asyncio.wait_for(process.stdout.readline(), 45):
                line = raw.decode('utf-8').strip()
                lines.append(line)
                if not line.startswith('PAPER_SKETCH_REQUEST '):
                    continue
                path = Path(line.removeprefix('PAPER_SKETCH_REQUEST '))
                request = json.loads(path.read_text(encoding='utf-8'))
                self.assertEqual(request['kind'], 'text')
                requests.append(request)
                prompt = request['config']['system_instruction']
                if prompt == system_prompt('retriever'):
                    pool = json.loads((ROOT / 'data/plot/ref.json').read_text(encoding='utf-8'))
                    text = json.dumps({'top10_plots': [row['id'] for row in pool[:9 if scenario == 'invalid_ids' else 10]]})
                elif prompt == system_prompt('planner'):
                    text = 'Initial plot description: A=10, B=15, C=12.'
                elif prompt == system_prompt('stylist'):
                    text = 'Styled plot description: A=10, B=15, C=12; muted palette.'
                elif prompt == system_prompt('visualizer'):
                    visualizers += 1
                    code = f'# render {visualizers}\n' + CODE
                    if scenario == 'clip_bug':
                        code += ('\nfrom matplotlib.collections import LineCollection\n'
                                 'for bar in ax.patches:\n'
                                 '    strokes = LineCollection([[(-1, 0), (4, 15)]])\n'
                                 '    strokes.set_clip_path(bar)\n'
                                 '    ax.add_collection(strokes)\n')
                    if scenario == 'all_invalid' or (scenario == 'render_failure' and visualizers > 2):
                        code = 'this is invalid Python!!!'
                    if scenario == 'timeout':
                        code = 'while True: pass'
                    if scenario == 'no_figure':
                        code = 'value = 42'
                    text = '```python\n' + code + '\n```'
                elif prompt == system_prompt('critic'):
                    critics += 1
                    if scenario == 'malformed' or (scenario == 'final_failure' and request['review_validation']['final']):
                        text = '{}'
                    elif scenario in ('revise', 'render_failure') and critics == 1:
                        text = json.dumps({'critic_suggestions': 'Correct the labels.',
                                           'revised_description': 'FIXED: A=10, B=15, C=12; clear labels.'})
                    else:
                        text = json.dumps({'critic_suggestions': 'No changes needed.',
                                           'revised_description': 'No changes needed.'})
                else:
                    self.fail('Unexpected system prompt')
                write_json(path.with_name('response.json'), {'id': request['id'], 'text': text,
                    'host': {'type': 'independent-codex',
                             'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                             'response_sha256': hashlib.sha256(text.encode()).hexdigest()}})
            _, stderr = await process.communicate()
            return output, requests, process.returncode, stderr.decode('utf-8'), lines
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    def test_upstream_files_and_prompts_match_recorded_import_path_changes(self):
        manifest = json.loads((VENDOR / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['commit'], 'f1da3db8d5f4c3add947dfd3ddd93dddd3394dc3')
        for name, entry in manifest['files'].items():
            source = ROOT / 'reference/PaperBanana' / name
            copied = (VENDOR / name).read_bytes()
            if source.exists():
                raw = source.read_bytes()
            else:
                restored = copied.decode('utf-8')
                for replacement in reversed(entry['replacements']):
                    restored = restored.replace(replacement['after'], replacement['before'])
                raw = restored.encode('utf-8')
            self.assertEqual(hashlib.sha256(raw).hexdigest(), entry['source_sha256'])
            expected = raw.decode('utf-8')
            for replacement in entry['replacements']:
                expected = expected.replace(replacement['before'], replacement['after'])
            self.assertEqual(copied, expected.encode('utf-8') if entry['replacements'] else raw)
            self.assertEqual(hashlib.sha256(copied).hexdigest(), entry['vendored_sha256'])
        for agent in ('retriever', 'planner', 'stylist', 'visualizer', 'critic'):
            original_path = ROOT / f'reference/PaperBanana/agents/{agent}_agent.py'
            if not original_path.exists():
                continue
            original = ast.parse(original_path.read_text(encoding='utf-8'))
            key = f'PLOT_{agent.upper()}_AGENT_SYSTEM_PROMPT'
            value = next(ast.literal_eval(n.value) for n in original.body if isinstance(n, ast.Assign)
                         and any(isinstance(t, ast.Name) and t.id == key for t in n.targets))
            self.assertEqual(system_prompt(agent), value)

    async def test_full_pool_ten_actual_images_and_original_order(self):
        with TemporaryDirectory() as directory:
            output, requests, code, stderr, _ = await self.run_fixture(Path(directory))
            self.assertEqual(code, 0, stderr)
            self.assertEqual([r['config']['system_instruction'] for r in requests],
                [system_prompt(a) for a in ('retriever', 'planner', 'stylist', 'visualizer', 'visualizer', 'critic')])
            pool = json.loads((ROOT / 'data/plot/ref.json').read_text(encoding='utf-8'))
            retrieval_text = requests[0]['turns'][0]['content'][0]['text']
            for row in pool:
                self.assertIn(f"Plot ID: {row['id']}\n", retrieval_text)
                self.assertIn(str(row['content']), retrieval_text)
            planner_parts = requests[1]['turns'][0]['content']
            images = [part for part in planner_parts if part['type'] == 'image']
            self.assertEqual(len(images), 10)
            for row, image in zip(pool[:10], images):
                self.assertEqual(Path(image['path']).read_bytes(), (ROOT / 'data/plot' / row['path_to_gt_image']).read_bytes())
                self.assertIn(json.dumps(row['content']), ''.join(p['text'] for p in planner_parts if p['type'] == 'text'))
            data = await load_result(output / 'result.json')
            self.assertEqual(data['task_name'], 'plot')
            self.assertEqual(data['final_review']['status'], 'passed')
            self.assertTrue(data['final_review']['reused_existing_review'])
            self.assertEqual(len(data['plot_execution_history']), 2)
            self.assertTrue(all(c['status'] == 'succeeded' for c in data['plot_execution_history']))
            self.assertEqual(data['execution_record']['bridge_request_counts']['image'], 0)
            self.assertEqual((output / 'final.py').read_text(encoding='utf-8'), '# render 2\n' + CODE.strip())
            self.assertEqual(data['content'], {'A': 10, 'B': 15, 'C': 12})
            self.assertTrue(all(c['renderer']['dpi'] == 300 for c in data['plot_execution_history']))
            # Python 실행 결과의 실제 막대 높이 대조
            import matplotlib
            matplotlib.use('Agg', force=True)
            import matplotlib.pyplot as plt
            exec((output / 'final.py').read_text(encoding='utf-8'), {})
            self.assertEqual([bar.get_height() for bar in plt.gca().patches], [10, 15, 12])
            plt.close('all')
            from paperbanana_plot.utils.plot_execution import execute_plot_code_worker
            self.assertEqual(execute_plot_code_worker(CODE), data['target_plot_desc0_base64_jpg'])
            selection = Path(directory) / 'selected'
            for args in [
                ['inspect', '--prior', str(output / 'result.json')],
                ['select', '--prior', str(output / 'result.json'), '--image-field', 'target_plot_desc0_base64_jpg', '--output', str(selection)],
            ]:
                process = await asyncio.create_subprocess_exec(sys.executable, '-B', str(SCRIPTS / 'run.py'), *args,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                _, errors = await process.communicate()
                self.assertEqual(process.returncode, 0, errors.decode('utf-8'))
            self.assertEqual((selection / 'final.py').read_text(encoding='utf-8'), '# render 1\n' + CODE.strip())
            selected = await load_result(selection / 'result.json')
            self.assertEqual(selected['eval_image_field'], 'target_plot_desc0_base64_jpg')
            self.assertEqual(selected['final_review']['status'], 'not_reviewed')
            (Path(directory) / 'feedback.txt').write_text('Change colors', encoding='utf-8')
            process = await asyncio.create_subprocess_exec(sys.executable, '-B', str(SCRIPTS / 'run.py'),
                'refine', '--prior', str(output / 'result.json'), '--dataset-dir', str(ROOT / 'data/plot'),
                '--feedback-file', str(Path(directory) / 'feedback.txt'), '--output', str(Path(directory) / 'rejected'),
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, errors = await process.communicate()
            self.assertNotEqual(process.returncode, 0)
            self.assertIn('PBInteract refinement is not connected', errors.decode('utf-8'))
            self.assertFalse(list((Path(directory) / 'rejected/requests').iterdir()))
            metadata = json.loads((output / 'state.json').read_text(encoding='utf-8'))
            (output / metadata['versions'][0]['code']).write_text('corrupted', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'code export'):
                await load_result(output / 'result.json')

    async def test_revision_reaches_code_and_final_review_adds_no_render(self):
        with TemporaryDirectory() as directory:
            output, requests, code, stderr, _ = await self.run_fixture(Path(directory), mode='none', scenario='revise')
            self.assertEqual(code, 0, stderr)
            data = await load_result(output / 'result.json')
            self.assertEqual(len(data['plot_execution_history']), 3)
            self.assertEqual(data['eval_image_field'], 'target_plot_critic_desc0_base64_jpg')
            self.assertEqual(data['final_review']['status'], 'passed')
            self.assertFalse(data['final_review']['reused_existing_review'])
            self.assertIn('FIXED:', requests[-2]['turns'][0]['content'][0]['text'])
            self.assertEqual(sum(r['config']['system_instruction'] == system_prompt('critic') for r in requests), 2)

    async def test_clip_fix_is_rendered_and_saved_with_original_response(self):
        with TemporaryDirectory() as directory:
            output, _, code, stderr, _ = await self.run_fixture(Path(directory), mode='none', scenario='clip_bug', rounds=0)
            self.assertEqual(code, 0, stderr)
            data = await load_result(output / 'result.json')
            field = data['eval_image_field'].removesuffix('_base64_jpg')
            raw = data[field + '_code']
            executed = data[field + '_executed_code']
            self.assertLess(raw.index('strokes.set_clip_path'), raw.index('ax.add_collection'))
            self.assertLess(executed.index('ax.add_collection'), executed.index('strokes.set_clip_path'))
            self.assertEqual((output / 'final.py').read_text(encoding='utf-8'), executed)
            for call in data['plot_execution_history']:
                self.assertEqual(len(call['repairs']), 1)
                self.assertEqual(hashlib.sha256((output / call['job'] / 'code.py').read_bytes()).hexdigest(),
                                 call['executed_code_sha256'])
            import numpy as np
            import matplotlib.pyplot as plt
            namespace = {}
            exec(executed, namespace)
            namespace['fig'].canvas.draw()
            for collection, bar in zip(namespace['ax'].collections, namespace['ax'].patches):
                self.assertTrue(np.allclose(collection.get_clip_box().extents, bar.get_window_extent().extents))
            plt.close('all')

    async def test_invalid_reference_selection_stops_before_planner(self):
        with TemporaryDirectory() as directory:
            output, requests, code, _, _ = await self.run_fixture(Path(directory), scenario='invalid_ids')
            self.assertNotEqual(code, 0)
            self.assertEqual(len(requests), 1)
            self.assertFalse((output / 'result.json').exists())
            self.assertTrue((output / 'failure.json').exists())

    async def test_failed_revision_preserves_last_valid_image(self):
        with TemporaryDirectory() as directory:
            output, _, code, stderr, _ = await self.run_fixture(Path(directory), mode='random', scenario='render_failure')
            self.assertEqual(code, 0, stderr)
            data = await load_result(output / 'result.json')
            self.assertEqual(data['eval_image_field'], 'target_plot_stylist_desc0_base64_jpg')
            self.assertEqual(data['plot_execution_history'][-1]['status'], 'invalid_code')
            self.assertEqual(data['plot_generation_status'], 'completed_with_plot_failures')
            self.assertEqual(summarize_result(data)['image_generation_status'], 'completed_with_plot_failures')
            self.assertEqual(data['final_review']['status'], 'issues_remaining')
            self.assertNotIn('target_plot_critic_desc0_base64_jpg', data)

    async def test_all_invalid_and_no_figure_preserve_failed_attempts(self):
        for scenario in ('all_invalid', 'no_figure'):
            with self.subTest(scenario=scenario), TemporaryDirectory() as directory:
                output, _, code, _, _ = await self.run_fixture(Path(directory), mode='none', scenario=scenario, rounds=0)
                self.assertNotEqual(code, 0)
                data = json.loads((output / 'failed_record.json').read_text(encoding='utf-8'))
                self.assertEqual([c['status'] for c in data['plot_execution_history']], ['invalid_code'] * 2)
                self.assertIn('target_plot_desc0_code', data)
                self.assertFalse((output / 'result.json').exists())

    async def test_timeout_is_bounded_and_records_failure(self):
        with TemporaryDirectory() as directory:
            started = time.monotonic()
            output, _, code, _, _ = await self.run_fixture(Path(directory), mode='none', scenario='timeout', rounds=0, plot_timeout=0.4)
            self.assertNotEqual(code, 0)
            data = json.loads((output / 'failed_record.json').read_text(encoding='utf-8'))
            self.assertEqual([c['status'] for c in data['plot_execution_history']], ['timeout'] * 2)
            self.assertLess(time.monotonic() - started, 15)

    async def test_malformed_critic_stops_and_final_failure_keeps_valid_plot(self):
        for scenario, rounds in [('malformed', 1), ('final_failure', 0)]:
            with self.subTest(scenario=scenario), TemporaryDirectory() as directory:
                output, requests, code, _, _ = await self.run_fixture(Path(directory), mode='none', scenario=scenario, rounds=rounds)
                self.assertEqual(sum(r['config']['system_instruction'] == system_prompt('visualizer') for r in requests), 2)
                if scenario == 'malformed':
                    self.assertNotEqual(code, 0)
                    self.assertTrue((output / 'failure.json').exists())
                else:
                    self.assertEqual(code, 0)
                    data = await load_result(output / 'result.json')
                    self.assertEqual(data['final_review']['status'], 'review_failed')


if __name__ == '__main__':
    unittest.main()
