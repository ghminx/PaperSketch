"""실제 동기 CLI의 비율 전달·수정·최종 검토 계약 검증."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'skills/paper-sketch/scripts'
sys.path.insert(0, str(SCRIPTS))
from respond import image_prompt
from review_protocol import context_hash


class CanvasConstraintTests(unittest.TestCase):
    def test_ratio_change_invalidates_previous_review_context(self):
        data = {'content': 'Input -> Encoder -> Prediction', 'visual_intent': 'Architecture',
                'additional_info': {'rounded_ratio': '16:9'}}
        before = context_hash(data)
        data['additional_info']['rounded_ratio'] = '21:9'
        self.assertNotEqual(context_hash(data), before)

    def test_plot_review_context_keeps_its_existing_contract(self):
        data = {'task_name': 'plot', 'content': {'A': 10}, 'visual_intent': 'Bar chart'}
        original = {'content': data['content'], 'caption': data['visual_intent'], 'requests': []}
        expected = hashlib.sha256(json.dumps(original, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.assertEqual(context_hash(data), expected)

    def test_image_prompt_prioritizes_setting_over_conflicting_description(self):
        original = 'Draw three modules on a 3:1 canvas.'
        prompt = image_prompt({'kind': 'image', 'config': {'image_config': {'aspect_ratio': '16:9'}},
                              'turns': [{'role': 'user', 'content': [{'type': 'text', 'text': original}]}]})
        self.assertIn(original, prompt)
        self.assertIn('takes precedence', prompt)
        self.assertIn('16:9', prompt.rsplit(original, 1)[1])

    def test_sync_generation_passes_ratio_to_every_stage_without_changing_input(self):
        with TemporaryDirectory() as temporary:
            work = Path(temporary)
            source = {'content': 'Input -> Encoder -> Prediction', 'visual_intent': 'Architecture',
                      'additional_info': {'rounded_ratio': '16:9'}}
            input_path = work / 'input.json'
            input_path.write_text(json.dumps(source), encoding='utf-8')
            fixture = work / 'image.png'
            Image.new('RGB', (160, 90), 'white').save(fixture)
            before = fixture.read_bytes()
            out = work / 'out'
            texts = ['Three modules on a 16:9 canvas.', 'Styled modules on a 16:9 canvas.',
                     json.dumps({'critic_suggestions': 'Use thinner arrows.',
                                 'revised_description': 'Three modules with thin arrows on 16:9.'}),
                     json.dumps({'critic_suggestions': 'No changes needed.',
                                 'revised_description': 'No changes needed.'})]
            seen = []
            with (work / 'stdout.log').open('wb') as stdout, (work / 'stderr.log').open('wb') as stderr:
                process = subprocess.Popen([sys.executable, '-B', str(SCRIPTS / 'run.py'), 'generate',
                    '--input', str(input_path), '--dataset-dir', str(work), '--output', str(out),
                    '--retrieval', 'none', '--critic-rounds', '1', '--timeout', '10'],
                    stdout=stdout, stderr=stderr)
                try:
                    deadline = time.monotonic() + 25
                    while process.poll() is None and time.monotonic() < deadline:
                        for path in out.glob('requests/*/request.json'):
                            if path.with_name('response.json').exists():
                                continue
                            request = json.loads(path.read_text(encoding='utf-8'))
                            if request['kind'] == 'text':
                                self.assertEqual(request['canvas_constraint']['aspect_ratio'], '16:9')
                                constraint = request['turns'][-1]['content'][-1]['text']
                                self.assertIn('16:9', constraint)
                                self.assertIn('takes precedence', constraint)
                                text = texts[len(seen)]
                                seen.append(request.get('review_validation', {}).get('final', False))
                                reply = {'text': text, 'host': {'type': 'independent-codex',
                                    'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                    'response_sha256': hashlib.sha256(text.encode()).hexdigest()}}
                            else:
                                self.assertEqual(request['config']['image_config']['aspect_ratio'], '16:9')
                                reply = {'image_path': str(fixture)}
                            response = path.with_name('response.json')
                            temp = response.with_suffix('.tmp')
                            temp.write_text(json.dumps({'id': request['id'], **reply}), encoding='utf-8')
                            temp.replace(response)
                        time.sleep(.02)
                    self.assertEqual(process.wait(timeout=5), 0, (work / 'stderr.log').read_text(encoding='utf-8'))
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.wait()
            self.assertEqual(seen, [False, False, False, True])
            result = json.loads((out / 'result.json').read_text(encoding='utf-8'))
            self.assertEqual(result['content'], source['content'])
            self.assertEqual(result['final_review']['status'], 'passed')
            self.assertEqual(fixture.read_bytes(), before)
            self.assertEqual(len(list(out.glob('requests/*/request.json'))), 7)


if __name__ == '__main__':
    unittest.main()
