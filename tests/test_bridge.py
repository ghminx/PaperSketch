import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/paper-sketch/scripts'))
from bridge import FileBridge, install_bridge, write_json


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = TemporaryDirectory()
        cls.directory = Path(cls.temp.name)
        cls.bridge = FileBridge(cls.directory, timeout=3)
        install_bridge(cls.bridge)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    async def handle(self, expected_kind, reply):
        """미응답 요청에 단일 fixture 응답 제출."""
        for _ in range(100):
            for path in self.directory.glob('*/request.json'):
                if not (path.parent / 'response.json').exists():
                    request = json.loads(path.read_text(encoding='utf-8'))
                    self.assertEqual(request['kind'], expected_kind)
                    write_json(path.parent / 'response.json', {'id': request['id'], **reply})
                    return request
            await asyncio.sleep(0.02)
        self.fail('No pending request')

    async def test_original_planner_builds_prompt_and_receives_text(self):
        from agents.planner_agent import PlannerAgent, DIAGRAM_PLANNER_AGENT_SYSTEM_PROMPT
        cfg = SimpleNamespace(main_model_name='codex-host', temperature=1.0)
        data = {'content': 'SOURCE-CONTENT', 'visual_intent': 'CAPTION', 'top10_references': []}
        task = asyncio.create_task(PlannerAgent(exp_config=cfg).process(data))
        req = await self.handle('text', {'text': '  Three modules connected by arrows.  '})
        result = await task
        self.assertEqual(req['config']['system_instruction'], DIAGRAM_PLANNER_AGENT_SYSTEM_PROMPT)
        self.assertIn('SOURCE-CONTENT', req['turns'][0]['content'][-1]['text'])
        self.assertEqual(result['target_diagram_desc0'], 'Three modules connected by arrows.')
        self.assertNotIn('target_diagram_desc0_base64_jpg', result)

    async def test_original_visualizer_converts_fixture_image(self):
        from agents.visualizer_agent import VisualizerAgent
        from PIL import Image
        png = self.directory / 'fixture.png'
        Image.new('RGB', (16, 16), 'white').save(png)
        cfg = SimpleNamespace(image_gen_model_name='codex-image-host', temperature=1.0)
        task = asyncio.create_task(VisualizerAgent(exp_config=cfg).process({'target_diagram_desc0': 'fixture description'}))
        req = await self.handle('image', {'image_path': str(png)})
        result = await task
        self.assertIn('fixture description', req['turns'][0]['content'][0]['text'])
        image = Image.open(io.BytesIO(base64.b64decode(result['target_diagram_desc0_base64_jpg'])))
        self.assertEqual(image.format, 'JPEG')
        self.assertEqual(image.size, (16, 16))

    async def test_original_pbinteract_preserves_multiturn_and_gating(self):
        from agents.refiner.pb_interact import PBInteract
        from PIL import Image
        buf = io.BytesIO()
        Image.new('RGB', (16, 16), 'white').save(buf, format='JPEG')
        encoded = base64.b64encode(buf.getvalue()).decode()
        field = 'target_diagram_desc0_base64_jpg'
        data = {'content': 'SOURCE', 'visual_intent': 'CAPTION', 'eval_image_field': field,
                field: encoded, 'target_diagram_desc0': 'SECRET_DESCRIPTION',
                'current_critic_round': [1, 0], 'chat_history': [
                    {'role': 'assistant', 'content': 'Generated.'},
                    {'role': 'user', 'content': 'Make the encoder blue.'}]}
        task = asyncio.create_task(PBInteract(exp_config=SimpleNamespace(main_model_name='codex-host', temperature=1.0)).process(data))
        context = await self.handle('text', {'text': '{"context_diagram1":"white fixture", "context_user_turn1":"blue encoder"}'})
        self.assertTrue(any(p['type'] == 'image' and Path(p['path']).exists() for p in context['turns'][0]['content']))
        critique = await self.handle('text', {'text': '{"critique_latest_turn":"Needs blue encoder"}'})
        self.assertNotIn('SECRET_DESCRIPTION', json.dumps(critique))
        gating = await self.handle('text', {'text': 'YES'})
        self.assertEqual([t['role'] for t in gating['turns']], ['user', 'model', 'user'])
        rewrite = await self.handle('text', {'text': '{"critic_suggestions":"Blue encoder", "revised_description":"A blue encoder."}'})
        self.assertIn('SECRET_DESCRIPTION', json.dumps(rewrite))
        result = await task
        self.assertEqual(result['target_diagram_critic_desc1-0'], 'A blue encoder.')

    async def test_pbinteract_next_review_excludes_previous_rewrite_description(self):
        """설명 공개 경계와 다음 round의 명시적 대화 초기화 확인."""
        from agents.refiner.pb_interact import PBInteract
        from respond_text import text_prompt
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (32, 18), 'white').save(buffer, format='JPEG')
        encoded = base64.b64encode(buffer.getvalue()).decode()
        field = 'target_diagram_desc0_base64_jpg'
        data = {'content': 'SOURCE', 'visual_intent': 'CAPTION', 'eval_image_field': field,
                field: encoded, 'target_diagram_desc0': 'HIDDEN_OLD_DESCRIPTION',
                'current_critic_round': [1, 0], 'chat_history': [
                    {'role': 'assistant', 'content': 'Generated.'},
                    {'role': 'user', 'content': 'Connect both heads.'}]}
        agent = PBInteract(exp_config=SimpleNamespace(main_model_name='codex-host', temperature=1.0))
        task = asyncio.create_task(agent.process(data))
        context = await self.handle('text', {'text': '{"context_diagram1":"one head", "context_user_turn1":"both heads"}'})
        critique = await self.handle('text', {'text': '{"critique_latest_turn":"Missing connection"}'})
        gating = await self.handle('text', {'text': 'YES'})
        rewrite = await self.handle('text', {'text': '{"critic_suggestions":"Fix connection", "revised_description":"HIDDEN_NEW_DESCRIPTION"}'})
        for request in (context, critique, gating):
            prompt, _ = text_prompt(request)
            self.assertNotIn('HIDDEN_OLD_DESCRIPTION', prompt)
        prompt, _ = text_prompt(rewrite)
        self.assertIn('HIDDEN_OLD_DESCRIPTION', prompt)
        self.assertIn('Missing connection', prompt)
        result = await task
        next_field = 'target_diagram_critic_desc1-0_base64_jpg'
        result[next_field] = encoded
        result['eval_image_field'] = next_field
        result['current_critic_round'] = [1, 1]
        task = asyncio.create_task(agent.process(result))
        next_review = await self.handle('text', {'text': '{"critique_latest_turn":"Both heads checked"}'})
        next_gating = await self.handle('text', {'text': 'NO'})
        for request in (next_review, next_gating):
            prompt, _ = text_prompt(request)
            self.assertNotIn('HIDDEN_OLD_DESCRIPTION', prompt)
            self.assertNotIn('HIDDEN_NEW_DESCRIPTION', prompt)
            self.assertIn('Connect both heads.', prompt)
        self.assertEqual(len(next_review['turns']), 1)
        await task

    async def test_error_and_timeout_are_not_success(self):
        task = asyncio.create_task(self.bridge.call('host', [{'type':'text','text':'test'}], {}))
        await self.handle('text', {'error': 'host failed'})
        with self.assertRaisesRegex(RuntimeError, 'host failed'):
            await task
        with TemporaryDirectory() as directory:
            with self.assertRaises(TimeoutError):
                await FileBridge(Path(directory), timeout=0).call('host', [], {})

    async def test_full_processor_generation_and_two_feedback_turns(self):
        """원본 전체 생성·재생성·2회 피드백과 수렴 분기 확인."""
        from run import make_processor, generate, refine, save_result, load_result
        from PIL import Image
        image_path = self.directory / 'processor-fixture.png'
        Image.new('RGB', (32, 18), 'white').save(image_path)
        image_reply = {'image_path': str(image_path)}
        processor = make_processor(self.directory, 'none', 2, 2, guard_reviews=False)
        task = asyncio.create_task(generate(processor, {
            'content': 'SOURCE', 'visual_intent': 'CAPTION', 'max_critic_rounds': 2}))
        await self.handle('text', {'text': 'Planner description.'})
        await self.handle('text', {'text': 'Stylist description.'})
        await self.handle('image', image_reply)
        await self.handle('image', image_reply)
        await self.handle('text', {'text': json.dumps({
            'critic_suggestions': 'Improve arrows.', 'revised_description': 'Revised arrows.'})})
        await self.handle('image', image_reply)
        await self.handle('text', {'text': json.dumps({
            'critic_suggestions': 'No changes needed.', 'revised_description': 'No changes needed.'})})
        data = await task
        initial = 'target_diagram_critic_desc0_base64_jpg'
        self.assertEqual(data['eval_image_field'], initial)
        self.assertIn('target_diagram_desc0_base64_jpg', data)
        self.assertIn('target_diagram_stylist_desc0_base64_jpg', data)
        self.assertNotIn('target_diagram_critic_desc1_base64_jpg', data)
        task = asyncio.create_task(refine(processor, data, 'Make encoder blue.'))
        await self.handle('text', {'text': json.dumps({'context_diagram1': 'white', 'context_user_turn1': 'blue encoder'})})
        await self.handle('text', {'text': '{"critique_latest_turn":"Encoder needs blue."}'})
        await self.handle('text', {'text': 'YES'})
        await self.handle('text', {'text': '{"critic_suggestions":"Blue encoder.","revised_description":"A blue encoder."}'})
        await self.handle('image', image_reply)
        followup = await self.handle('text', {'text': '{"critique_latest_turn":"Blue encoder is satisfied."}'})
        self.assertIn('ALREADY', followup['config']['system_instruction'])
        await self.handle('text', {'text': 'NO'})
        data = await task
        revised = 'target_diagram_critic_desc1-0_base64_jpg'
        self.assertEqual(data['eval_image_field'], revised)
        self.assertEqual(data['prior_preferred_candidates'], [initial])
        self.assertEqual(len(data['chat_history']), 3)
        task = asyncio.create_task(refine(processor, data, 'Keep the blue encoder.'))
        context = await self.handle('text', {'text': json.dumps({
            'context_diagram1': 'white', 'context_user_turn1': 'blue encoder',
            'context_diagram2': 'blue encoder', 'context_user_turn2': 'keep blue'})})
        images = [p for p in context['turns'][0]['content'] if p['type'] == 'image']
        self.assertEqual(len(images), 2)
        critique = await self.handle('text', {'text': json.dumps({
            'critique_latest_turn': 'Already satisfied.', 'critique_prior_turn1': 'Blue preserved.'})})
        self.assertIn('critique_prior_turn1', json.dumps(critique))
        self.assertIn('Make encoder blue.', json.dumps(critique))
        await self.handle('text', {'text': 'NO'})
        data = await task
        self.assertEqual(data['eval_image_field'], revised)
        self.assertEqual(data['prior_preferred_candidates'], [initial, revised])
        self.assertEqual(len(data['chat_history']), 5)
        with TemporaryDirectory() as directory:
            output = Path(directory)
            await save_result(output, data)
            restored = await load_result(output / 'result.json')
            self.assertEqual(restored, data)
            self.assertEqual((output / 'final.jpg').read_bytes(), base64.b64decode(data[revised]))
        with self.assertRaisesRegex(ValueError, 'Feedback must not be empty'):
            await refine(processor, data, ' ')

    async def test_initial_critic_render_failure_keeps_last_good_image(self):
        """최초 Critic 재생성 실패가 원본 rollback 경로로 연결됨을 확인."""
        from run import make_processor, generate
        from PIL import Image
        image_path = self.directory / 'fallback-fixture.png'
        Image.new('RGB', (32,18), 'white').save(image_path)
        processor = make_processor(self.directory, 'none', 3, 1, guard_reviews=False)
        task = asyncio.create_task(generate(processor, {
            'content':'SOURCE', 'visual_intent':'CAPTION', 'max_critic_rounds':3}))
        await self.handle('text', {'text':'Planner.'})
        await self.handle('text', {'text':'Stylist.'})
        await self.handle('image', {'image_path':str(image_path)})
        await self.handle('image', {'image_path':str(image_path)})
        await self.handle('text', {'text':'{"critic_suggestions":"Fix arrow", "revised_description":"Fixed arrow"}'})
        await self.handle('image', {'error':'Unavailable', 'error_type':'unknown'})
        result = await asyncio.wait_for(task,1)
        self.assertEqual(result['eval_image_field'], 'target_diagram_stylist_desc0_base64_jpg')
        self.assertTrue(result['target_diagram_critic_desc0_gen_failed'])
        self.assertNotIn('target_diagram_critic_suggestions1', result)

    async def test_full_processor_respects_last_render_round_limit(self):
        """최종 허용 round에서 재생성 후 추가 Critic 호출 없이 종료 확인."""
        from run import make_processor, generate
        from PIL import Image
        image_path = self.directory / 'round-limit-fixture.png'
        Image.new('RGB', (32, 18), 'white').save(image_path)
        reply = {'image_path': str(image_path)}
        processor = make_processor(self.directory, 'none', 1, 1, guard_reviews=False)
        task = asyncio.create_task(generate(processor, {
            'content': 'SOURCE', 'visual_intent': 'CAPTION', 'max_critic_rounds': 1}))
        await self.handle('text', {'text': 'Planner.'})
        await self.handle('text', {'text': 'Stylist.'})
        await self.handle('image', reply)
        await self.handle('image', reply)
        await self.handle('text', {'text': '{"critic_suggestions":"Improve arrows.","revised_description":"Better arrows."}'})
        await self.handle('image', reply)
        data = await asyncio.wait_for(task, 1)
        self.assertEqual(data['current_critic_round'], 0)
        self.assertEqual(data['eval_image_field'], 'target_diagram_critic_desc0_base64_jpg')
        self.assertNotIn('target_diagram_critic_suggestions1', data)

    async def test_selected_saved_image_reaches_original_pbinteract(self):
        """선택·저장·재개한 다른 이미지가 실제 원본 문맥화에 전달됨을 확인."""
        from run import make_processor, refine
        from state import load_result, save_result, select_version
        from PIL import Image
        encoded = []
        for color in ['blue', 'white']:
            buffer = io.BytesIO()
            Image.new('RGB', (32, 18), color).save(buffer, format='JPEG')
            encoded.append(base64.b64encode(buffer.getvalue()).decode())
        data = {'content': 'SOURCE', 'visual_intent': 'CAPTION',
                'target_diagram_desc0': 'Blue Planner.', 'target_diagram_desc0_base64_jpg': encoded[0],
                'target_diagram_stylist_desc0': 'White Stylist.', 'target_diagram_stylist_desc0_base64_jpg': encoded[1],
                'eval_image_field': 'target_diagram_stylist_desc0_base64_jpg',
                'chat_history': [{'role': 'assistant', 'content': 'Generated.'}]}
        with TemporaryDirectory() as directory:
            output = Path(directory)
            await save_result(output, select_version(data, 'target_diagram_desc0_base64_jpg'), action='select')
            restored = await load_result(output / 'result.json')
        task = asyncio.create_task(refine(make_processor(self.directory, 'none', 1, 1, guard_reviews=False), restored, 'Keep blue.'))
        request = await self.handle('text', {'text': '{"context_diagram1":"blue","context_user_turn1":"keep blue"}'})
        image = next(p for p in request['turns'][0]['content'] if p['type'] == 'image')
        self.assertEqual(Path(image['path']).read_bytes(), base64.b64decode(encoded[0]))
        await self.handle('text', {'text': '{"critique_latest_turn":"Blue retained."}'})
        await self.handle('text', {'text': 'NO'})
        result = await task
        self.assertEqual(result['eval_image_field'], 'target_diagram_desc0_base64_jpg')
        self.assertEqual(result['prior_preferred_candidates'], ['target_diagram_desc0_base64_jpg'])

    @unittest.skipUnless((ROOT / 'data/diagram/ref.json').exists(), 'Prepared MTP dataset required')
    async def test_real_auto_pool_and_planner_images_are_connected(self):
        """실제 200개 후보 요청과 선택된 10개 이미지의 byte 연결 확인."""
        from agents.retriever_agent import RetrieverAgent
        from agents.planner_agent import PlannerAgent
        dataset = ROOT / 'data/diagram'
        pool = json.loads((dataset / 'ref.json').read_text(encoding='utf-8'))
        ids = [r['id'] for r in pool[:10]]
        cfg = SimpleNamespace(main_model_name='host', temperature=1.0, dataset_dir=dataset)
        task = asyncio.create_task(RetrieverAgent(exp_config=cfg).process(
            {'content': 'TARGET METHOD', 'visual_intent': 'TARGET CAPTION'}, retrieval_setting='auto'))
        request = await self.handle('text', {'text': json.dumps({'top10_diagrams': ids})})
        data = await task
        text = request['turns'][0]['content'][0]['text']
        self.assertEqual(text.count('- Diagram ID: '), 200)
        self.assertIn(f'- Diagram ID: {pool[199]["id"]}\n', text)
        self.assertNotIn(f'- Diagram ID: {pool[200]["id"]}\n', text)
        self.assertEqual(data['top10_references'], ids)
        task = asyncio.create_task(PlannerAgent(exp_config=cfg).process(data))
        request = await self.handle('text', {'text': 'Fixture plan after ten image inputs.'})
        result = await task
        images = [part for part in request['turns'][0]['content'] if part['type'] == 'image']
        self.assertEqual(len(images), 10)
        for part, record in zip(images, pool[:10]):
            self.assertEqual(Path(part['path']).read_bytes(), (dataset / record['path_to_gt_image']).read_bytes())
        self.assertEqual(result['target_diagram_desc0'], 'Fixture plan after ten image inputs.')

    async def test_roundtrip_probe_in_separate_python_process(self):
        """별도 Python의 요청 3개 처리 후 원본 생성·검토 결과 확인."""
        from PIL import Image
        with TemporaryDirectory() as directory:
            session = Path(directory)
            fixture = session / 'fixture.png'
            Image.new('RGB', (32, 18), 'white').save(fixture)
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(ROOT / 'skills/paper-sketch/scripts/probe.py'),
                '--exchange-dir', str(session), '--kind', 'roundtrip', '--timeout', '15',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

            async def service():
                replies = [
                    ('text', {'text': 'Three connected modules.'}),
                    ('image', {'image_path': str(fixture)}),
                    ('text', {'text': '{"critic_suggestions":"No changes needed.","revised_description":"No changes needed."}'})]
                for index, (kind, reply) in enumerate(replies):
                    line = (await process.stdout.readline()).decode().strip()
                    self.assertTrue(line.startswith('PAPER_SKETCH_REQUEST '), line)
                    path = Path(line.removeprefix('PAPER_SKETCH_REQUEST '))
                    request = json.loads(path.read_text(encoding='utf-8'))
                    self.assertEqual(request['kind'], kind)
                    if index == 2:
                        image_parts = [part for part in request['turns'][0]['content'] if part['type'] == 'image']
                        self.assertEqual(len(image_parts), 1)
                        with Image.open(image_parts[0]['path']) as image:
                            self.assertEqual(image.format, 'JPEG')
                    write_json(path.parent / 'response.json', {'id': request['id'], **reply})
                stdout, stderr = await process.communicate()
                self.assertEqual(process.returncode, 0, stderr.decode(errors='replace'))
                self.assertIn('complete', stdout.decode())

            try:
                await asyncio.wait_for(service(), timeout=25)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            result = json.loads((session / 'result.json').read_text(encoding='utf-8'))
            self.assertEqual(result['target_diagram_critic_suggestions0'], 'No changes needed.')
            self.assertEqual(result['target_diagram_critic_desc0'], result['target_diagram_desc0'])

    async def test_full_cli_default_ratio_matches_upstream_ui_and_image_prompt(self):
        """기본 입력이 원본 UI 비율로 원본 Visualizer·host prompt에 전달됨을 확인."""
        from PIL import Image
        from respond import image_prompt
        from state import load_result
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            write_json(source, {'content': 'SOURCE', 'visual_intent': 'CAPTION'})
            fixture = root / 'fixture.png'
            Image.new('RGB', (32, 18), 'white').save(fixture)
            output = root / 'run'
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(ROOT / 'skills/paper-sketch/scripts/run.py'), 'generate',
                '--input', str(source), '--dataset-dir', str(root), '--output', str(output),
                '--retrieval', 'none', '--critic-rounds', '0', '--timeout', '15',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

            async def service():
                for kind in ['text', 'text', 'image', 'image']:
                    while True:
                        line = (await process.stdout.readline()).decode().strip()
                        self.assertTrue(line)
                        if line.startswith('PAPER_SKETCH_REQUEST '):
                            break
                    path = Path(line.removeprefix('PAPER_SKETCH_REQUEST '))
                    request = json.loads(path.read_text(encoding='utf-8'))
                    self.assertEqual(request['kind'], kind)
                    if kind == 'text':
                        reply = {'text': 'Description.'}
                    else:
                        self.assertEqual(request['config']['image_config']['aspect_ratio'], '21:9')
                        prompt = image_prompt(request)
                        self.assertIn('aspect_ratio = 21:9', prompt)
                        original = request['turns'][0]['content'][0]['text']
                        self.assertIn(original, prompt)
                        self.assertIn('takes precedence', prompt.split(original, 1)[1])
                        reply = {'image_path': str(fixture)}
                    write_json(path.parent / 'response.json', {'id': request['id'], **reply})
                _, stderr = await process.communicate()
                self.assertEqual(process.returncode, 0, stderr.decode(errors='replace'))
            try:
                await asyncio.wait_for(service(), 25)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            result = await load_result(output / 'result.json')
            self.assertEqual(result['additional_info']['rounded_ratio'], '21:9')

    def test_vendored_sources_match_pinned_manifest(self):
        runtime = ROOT / 'skills/paper-sketch/assets/interact'
        manifest = json.loads((runtime / 'SOURCE_MANIFEST.json').read_text())
        for rel, digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256((runtime / rel).read_bytes()).hexdigest(), digest, rel)
            original = ROOT / 'reference/PaperBanana-Interact' / rel
            if original.exists():
                self.assertEqual((runtime / rel).read_bytes(), original.read_bytes())
        for rel, omitted in manifest['omitted_files'].items():
            self.assertFalse((runtime / rel).exists(), rel)
            original = ROOT / 'reference/PaperBanana-Interact' / rel
            if original.exists():
                self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), omitted['sha256'], rel)
            self.assertTrue(omitted['reason'])

    async def test_grouped_auto_selects_24_then_10_and_connects_planner(self):
        """실제 고정 그룹의 5회 검색·최종 전문·Planner 이미지 연결 확인."""
        from grouped_retriever import GroupedRetrieverAgent, REQUEST_CHAR_BUDGET
        from agents.planner_agent import PlannerAgent
        dataset = ROOT / 'data/diagram'
        groups = ROOT / 'data/diagram/retrieval'
        manifest = json.loads((groups / 'manifest.json').read_text(encoding='utf-8'))
        cfg = SimpleNamespace(main_model_name='host', temperature=1.0, dataset_dir=dataset)
        audit_path = self.directory / 'grouped-audit.json'
        agent = GroupedRetrieverAgent(exp_config=cfg, groups_dir=groups, audit_path=audit_path)
        task = asyncio.create_task(agent.process({'content': 'TARGET-METHOD', 'visual_intent': 'TARGET-CAPTION'}))
        shortlist = []
        for entry in manifest['groups']:
            ids = entry['ids'][-6:]
            shortlist.extend(ids)
            req = await self.handle('text', {'text': json.dumps({'selected_diagrams': ids})})
            text = req['turns'][0]['content'][0]['text']
            self.assertIn((groups / entry['text_file']).read_text(encoding='utf-8'), text)
            self.assertEqual(text.count('- Diagram ID: '), entry['records'])
            self.assertLessEqual(len(text) + len(req['config']['system_instruction']), REQUEST_CHAR_BUDGET)
            self.assertIn('TARGET-METHOD', text)
        final_ids = shortlist[::2][:10]
        request = await self.handle('text', {'text': json.dumps({'selected_diagrams': final_ids})})
        text = request['turns'][0]['content'][0]['text']
        pool = json.loads((dataset / 'ref.json').read_text(encoding='utf-8'))
        finalists = [row for row in pool[:200] if row['id'] in shortlist]
        self.assertEqual(text.count('- Diagram ID: '), 24)
        for row in finalists:
            self.assertIn(row['content'], text)
            self.assertIn(row['visual_intent'], text)
        self.assertLessEqual(len(text) + len(request['config']['system_instruction']), REQUEST_CHAR_BUDGET)
        data = await task
        self.assertEqual(data['top10_references'], final_ids)
        audit = json.loads(audit_path.read_text(encoding='utf-8'))
        self.assertEqual(audit, data['retrieval_audit'])
        self.assertEqual(audit['status'], 'complete')
        self.assertEqual([len(s['selected_ids']) for s in audit['stages']], [6, 6, 6, 6, 10])
        task = asyncio.create_task(PlannerAgent(exp_config=cfg).process(data))
        request = await self.handle('text', {'text': 'PLAN'})
        await task
        images = [part for part in request['turns'][0]['content'] if part['type'] == 'image']
        by_id = {row['id']: row for row in pool}
        self.assertEqual(len(images), 10)
        for part, refid in zip(images, final_ids):
            self.assertEqual(Path(part['path']).read_bytes(), (dataset / by_id[refid]['path_to_gt_image']).read_bytes())

    async def test_grouped_auto_rejects_invalid_selection_and_oversized_target(self):
        """중복·범위 외·개수 부족 응답과 과대 입력의 실패 확인."""
        from grouped_retriever import GroupedRetrieverAgent
        dataset = ROOT / 'data/diagram'
        groups = ROOT / 'data/diagram/retrieval'
        manifest = json.loads((groups / 'manifest.json').read_text(encoding='utf-8'))
        first_ids = manifest['groups'][0]['ids']
        cfg = SimpleNamespace(main_model_name='host', temperature=1.0, dataset_dir=dataset)
        for ids in ([first_ids[0]] * 6, first_ids[:5], first_ids[:5] + [manifest['groups'][1]['ids'][0]]):
            audit_path = self.directory / 'invalid-grouped-audit.json'
            agent = GroupedRetrieverAgent(exp_config=cfg, groups_dir=groups, audit_path=audit_path)
            task = asyncio.create_task(agent.process({'content': 'SOURCE', 'visual_intent': 'CAPTION'}))
            await self.handle('text', {'text': json.dumps({'selected_diagrams': ids})})
            with self.assertRaisesRegex(ValueError, 'distinct reference IDs'):
                await task
            audit = json.loads(audit_path.read_text(encoding='utf-8'))
            self.assertEqual(audit['stages'][0]['status'], 'invalid_response')
            self.assertNotIn('final_ids', audit)
        before = set(self.directory.glob('*/request.json'))
        agent = GroupedRetrieverAgent(exp_config=cfg, groups_dir=groups)
        with self.assertRaisesRegex(ValueError, 'character budget'):
            await agent.process({'content': 'x' * 300_000, 'visual_intent': 'CAPTION'})
        self.assertEqual(before, set(self.directory.glob('*/request.json')))

    async def test_grouped_auto_rejects_dataset_and_group_mismatch(self):
        """기준 데이터 hash와 고정 그룹 내용의 불일치 검출."""
        from grouped_retriever import GroupedRetrieverAgent
        dataset = ROOT / 'data/diagram'
        groups = ROOT / 'data/diagram/retrieval'
        with TemporaryDirectory() as directory:
            path = Path(directory)
            (path / 'ref.json').write_text('[]', encoding='utf-8')
            cfg = SimpleNamespace(main_model_name='host', temperature=1.0, dataset_dir=path)
            agent = GroupedRetrieverAgent(exp_config=cfg, groups_dir=groups)
            with self.assertRaisesRegex(ValueError, 'dataset hash'):
                await agent.process({'content': 'SOURCE', 'visual_intent': 'CAPTION'})
            cfg.dataset_dir = dataset
            manifest = json.loads((groups / 'manifest.json').read_text(encoding='utf-8'))
            for entry in manifest['groups']:
                for key in ('text_file', 'json_file'):
                    (path / entry[key]).write_bytes((groups / entry[key]).read_bytes())
            (path / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            (path / manifest['groups'][0]['text_file']).write_text('changed', encoding='utf-8')
            agent = GroupedRetrieverAgent(exp_config=cfg, groups_dir=path)
            with self.assertRaisesRegex(ValueError, 'content or size'):
                await agent.process({'content': 'SOURCE', 'visual_intent': 'CAPTION'})

    async def test_full_cli_grouped_auto_keeps_original_generation_and_audit(self):
        """실제 생성 CLI의 5회 검색·원본 후속 생성·검색 기록 저장 연결 확인."""
        import re
        from PIL import Image
        dataset = ROOT / 'data/diagram'
        groups = ROOT / 'data/diagram/retrieval'
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'input.json'
            write_json(source, {'content': 'SOURCE', 'visual_intent': 'CAPTION'})
            fixture = root / 'fixture.png'
            Image.new('RGB', (32, 18), 'white').save(fixture)
            output = root / 'run'
            process = await asyncio.create_subprocess_exec(
                sys.executable, '-B', str(ROOT / 'skills/paper-sketch/scripts/run.py'), 'generate',
                '--input', str(source), '--dataset-dir', str(dataset), '--reference-groups', str(groups),
                '--output', str(output), '--retrieval', 'auto', '--critic-rounds', '0', '--timeout', '15',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

            async def service():
                for index in range(10):
                    while True:
                        line = (await process.stdout.readline()).decode().strip()
                        self.assertTrue(line)
                        if line.startswith('PAPER_SKETCH_REQUEST '):
                            break
                    path = Path(line.removeprefix('PAPER_SKETCH_REQUEST '))
                    request = json.loads(path.read_text(encoding='utf-8'))
                    if index < 5:
                        candidates = re.findall(r'^- Diagram ID: (.+)$', request['turns'][0]['content'][0]['text'], re.MULTILINE)
                        self.assertEqual(len(candidates), [53, 51, 58, 38, 24][index])
                        count = 6 if index < 4 else 10
                        reply = {'text': json.dumps({'selected_diagrams': candidates[:count]})}
                    elif index < 7:
                        reply = {'text': 'Fixture description.'}
                    elif index < 9:
                        self.assertEqual(request['kind'], 'image')
                        reply = {'image_path': str(fixture)}
                    else:
                        answer = json.dumps({'critic_suggestions': 'No changes needed.',
                                             'revised_description': 'No changes needed.'})
                        reply = {'text': answer, 'host': {'type': 'independent-codex',
                            'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                            'response_sha256': hashlib.sha256(answer.encode()).hexdigest()}}
                    write_json(path.parent / 'response.json', {'id': request['id'], **reply})
                _, stderr = await process.communicate()
                self.assertEqual(process.returncode, 0, stderr.decode(errors='replace'))
            try:
                await asyncio.wait_for(service(), 30)
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
            from state import load_result
            data = await load_result(output / 'result.json')
            audit = json.loads((output / 'retrieval.json').read_text(encoding='utf-8'))
            self.assertEqual(audit, data['retrieval_audit'])
            self.assertEqual(data['top10_references'], audit['final_ids'])
            self.assertEqual(audit['strategy'], 'grouped-4x6-to10')
            self.assertEqual(len(audit['stages']), 5)
            config = json.loads((output / 'run_config.json').read_text(encoding='utf-8'))
            self.assertEqual(config['requested_options']['retrieval'], 'auto')
            self.assertEqual(data['execution_record']['retrieval']['origin']['strategy'], audit['strategy'])
            self.assertEqual(data['eval_image_field'], 'target_diagram_stylist_desc0_base64_jpg')


if __name__ == '__main__':
    unittest.main()
