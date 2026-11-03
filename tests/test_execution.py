import asyncio
import base64
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT/'skills/paper-sketch/scripts'
sys.path.insert(0, str(SCRIPTS))
from bridge import write_json
from execution import observed_calls
from state import load_result, save_result, summarize_result


class ExecutionTests(unittest.IsolatedAsyncioTestCase):
    async def cli(self, root, action, *, mode='auto', prior=None, field=None, fail=False, dataset=None, groups=None):
        """실제 데이터와 정식 CLI를 사용하되 모델·이미지는 모의 응답으로 연결."""
        root.mkdir(parents=True)
        dataset = dataset or ROOT/'data/diagram'
        groups = groups or ROOT/'data/diagram/retrieval'
        output = root/'out'
        args = [sys.executable, '-B', str(SCRIPTS/'run.py'), action, '--output', str(output)]
        if action == 'generate':
            write_json(root/'input.json', {'content': 'SOURCE', 'visual_intent': 'CAPTION'})
            args += ['--input', str(root/'input.json'), '--retrieval', mode, '--critic-rounds', '0']
            if mode == 'auto': args += ['--reference-groups', str(groups)]
        if prior is not None: args += ['--prior', str(prior)]
        if action == 'select': args += ['--image-field', field]
        else: args += ['--dataset-dir', str(dataset), '--timeout', '5']
        if action == 'refine':
            (root/'feedback.txt').write_text('Preserve existing diagram', encoding='utf-8')
            args += ['--feedback-file', str(root/'feedback.txt')]
        process = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.PIPE)
        requests = []
        stdout = []
        try:
            while raw := await asyncio.wait_for(process.stdout.readline(), 20):
                line = raw.decode('utf-8').strip(); stdout.append(line)
                if not line.startswith('PAPER_SKETCH_REQUEST '): continue
                path = Path(line.removeprefix('PAPER_SKETCH_REQUEST '))
                request = json.loads(path.read_text(encoding='utf-8')); requests.append(request)
                response = {'id': request['id']}
                if request['kind'] == 'image':
                    fixture = root/f'fixture-{len(requests)}.png'
                    Image.new('RGB', (32, 18), 'blue' if len(requests) % 2 else 'white').save(fixture)
                    response['image_path'] = str(fixture)
                else:
                    text = json.dumps(request)
                    policy = request.get('review_validation')
                    candidates = re.findall(r'^- Diagram ID: (.+)$', request['turns'][0]['content'][0]['text'], re.M)
                    if candidates:
                        text = json.dumps({'selected_diagrams': candidates[:10 if len(candidates)==24 else 6]})
                    elif policy:
                        stage = policy['stage']
                        if stage == 'context':
                            fields = set(re.findall(r'context_(?:diagram|user_turn)\d+', text))
                            text = json.dumps({k: 'Fixture context' for k in fields})
                        elif stage == 'critique':
                            fields = set(re.findall(r'critique_(?:latest_turn|prior_turn\d+|source_content|presentation)', text))
                            text = '{}' if fail else json.dumps({k: 'No issues' for k in fields})
                        elif stage == 'gate': text = 'NO'
                        else: text = json.dumps({'critic_suggestions': 'No changes needed.',
                                                  'revised_description': 'No changes needed.'})
                    else: text = 'Fixture description'
                    response.update(text=text, host={'type': 'independent-codex',
                        'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'response_sha256': hashlib.sha256(text.encode()).hexdigest()})
                write_json(path.with_name('response.json'), response)
            _, errors = await process.communicate()
            if not fail: self.assertEqual(process.returncode, 0, errors.decode('utf-8'))
            else: self.assertNotEqual(process.returncode, 0)
            return output, requests, stdout
        finally:
            if process.returncode is None: process.kill(); await process.wait()

    async def test_fresh_preparation_groups_and_full_diagram_generation(self):
        from prepare_references import prepare_references
        from prepare_reference_groups import prepare_groups
        with TemporaryDirectory() as directory:
            root = Path(directory)
            dataset, groups = root/'prepared', root/'groups'
            prepare_references(ROOT/'data/diagram', dataset)
            prepare_groups(dataset, groups)
            output, requests, _ = await self.cli(root/'generated', 'generate', dataset=dataset, groups=groups)
            data = await load_result(output/'result.json')
            self.assertEqual(data['retrieval_audit']['candidate_count'], 200)
            self.assertEqual(len(data['top10_references']), 10)
            self.assertEqual(len(data['retrieval_audit']['stages']), 5)
            self.assertTrue(any(request['kind']=='image' for request in requests))

    async def test_cli_all_retrieval_modes_select_and_two_feedback_turns(self):
        for mode in ('auto', 'random', 'none'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                root = Path(directory)
                generated, requests, _ = await self.cli(root/'generate', 'generate', mode=mode)
                data = await load_result(generated/'result.json')
                origin = copy.deepcopy(data['execution_record']['retrieval']['origin'])
                self.assertEqual(origin['mode'], mode)
                self.assertEqual(origin['selected_ids'], data['top10_references'])
                self.assertEqual(len(requests), 10 if mode=='auto' else 5)
                self.assertEqual(data['execution_record']['bridge_request_counts']['image'], 2)
                before = (generated/'result.json').read_bytes()
                selected, requests, _ = await self.cli(root/'select', 'select', prior=generated/'result.json',
                                                       field='target_diagram_desc0_base64_jpg')
                self.assertEqual(requests, [])
                selected_data = await load_result(selected/'result.json')
                self.assertEqual(selected_data['execution_record']['parent']['selected_input']['image_field'],
                                 'target_diagram_stylist_desc0_base64_jpg')
                self.assertEqual(selected_data['execution_record']['selected_output']['image_field'],
                                 'target_diagram_desc0_base64_jpg')
                self.assertEqual((generated/'result.json').read_bytes(), before)
                prior = selected/'result.json'
                for turn in (1, 2):
                    prior_data = await load_result(prior)
                    out, requests, _ = await self.cli(root/f'refine-{turn}', 'refine', prior=prior)
                    data = await load_result(out/'result.json'); record = data['execution_record']
                    self.assertEqual(record['requested_options']['retrieval'], 'auto')
                    self.assertEqual(record['retrieval']['this_run'], 'not_run')
                    self.assertEqual(record['retrieval']['origin'], origin)
                    self.assertEqual(data['top10_references'], origin['selected_ids'])
                    self.assertEqual(record['bridge_request_counts'], {'text': 3, 'image': 0})
                    self.assertEqual(record['feedback_turn_count'], turn)
                    self.assertEqual(record['parent']['result_sha256'], hashlib.sha256(prior.read_bytes()).hexdigest())
                    self.assertEqual(record['parent']['selected_input']['image_sha256'],
                        hashlib.sha256(base64.b64decode(prior_data[prior_data['eval_image_field']])).hexdigest())
                    self.assertEqual(len(data['execution_history']), turn+1)
                    for request in requests:
                        self.assertNotIn('execution_record', json.dumps(request['turns']))
                    self.assertTrue(all(c['requested_model']=='unverified' and c['actual_tool']=='unverified'
                                        for c in record['calls']))
                    self.assertEqual(json.loads((out/'state.json').read_text(encoding='utf-8'))['execution'], record)
                    self.assertEqual(summarize_result(data)['execution'], record)
                    prior = out/'result.json'

    async def test_legacy_unknown_origin_does_not_infer_auto_and_survives_move(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            generated, _, _ = await self.cli(root/'generate', 'generate', mode='none')
            data = await load_result(generated/'result.json'); data.pop('execution_record')
            await save_result(root/'legacy', data)
            write_json(root/'legacy/run_config.json', {'retrieval': 'auto'})
            out, _, _ = await self.cli(root/'refine', 'refine', prior=root/'legacy/result.json')
            record = (await load_result(out/'result.json'))['execution_record']
            self.assertEqual(record['retrieval']['origin']['mode'], 'unverified')
            self.assertEqual(record['retrieval']['origin']['selected_ids'], [])
            shutil.copytree(out, root/'moved'); shutil.rmtree(root/'legacy')
            self.assertEqual((await load_result(root/'moved/result.json'))['execution_record'], record)

    async def test_failed_review_retains_execution_and_prior_input(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prior, _, _ = await self.cli(root/'generate', 'generate', mode='none')
            out, requests, _ = await self.cli(root/'failure', 'refine', prior=prior/'result.json', fail=True)
            data = json.loads((out/'failed_record.json').read_text(encoding='utf-8'))
            self.assertEqual(data['execution_record']['status'], 'failed')
            self.assertEqual(data['execution_record']['bridge_request_counts'], {'text': 3, 'image': 0})
            self.assertEqual(data['execution_record']['retrieval']['this_run'], 'not_run')
            self.assertFalse((out/'result.json').exists())
            self.assertTrue((prior/'result.json').exists())

    def test_model_evidence_and_invalid_or_unlinked_metadata(self):
        with TemporaryDirectory() as directory:
            path = Path(directory)/'requests/one/request.json'; path.parent.mkdir(parents=True)
            write_json(path, {'id':'one', 'kind':'text', 'model_name':'codex-host'})
            write_json(path.with_name('response.json'), {'id':'one', 'text':'fixture'})
            host = path.parent/'codex-host'; host.mkdir()
            metadata = {'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'requested_model':'fixture-requested-model', 'reasoning_effort':'high',
                        'exit_code':0, 'thread_ids':['fixture-thread']}
            write_json(host/'metadata.json', metadata)
            record = observed_calls([path])[0]
            self.assertEqual(record['requested_model'], 'fixture-requested-model')
            self.assertEqual(record['backend_model_version'], 'unverified')
            self.assertEqual(record['applied_sampling'], 'unverified')
            for raw in ('{bad', '[]', json.dumps({**metadata,'request_sha256':'wrong'}), '{}'):
                (host/'metadata.json').write_text(raw, encoding='utf-8')
                self.assertEqual(observed_calls([path])[0]['requested_model'], 'unverified')
            path.with_name('response.json').write_text('{bad', encoding='utf-8')
            self.assertEqual(observed_calls([path])[0]['response_status'], 'invalid_json')
            path.with_name('response.json').unlink()
            self.assertEqual(observed_calls([path])[0]['response_status'], 'missing')

    async def test_state_rejects_execution_metadata_disagreement(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            out, _, _ = await self.cli(root/'generate', 'generate', mode='none')
            state = json.loads((out/'state.json').read_text(encoding='utf-8'))
            state['execution']['status'] = 'invented'
            write_json(out/'state.json', state)
            with self.assertRaisesRegex(ValueError, 'execution metadata'):
                await load_result(out/'result.json')


if __name__ == '__main__':
    unittest.main()
