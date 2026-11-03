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

ROOT=Path(__file__).resolve().parents[1]
SCRIPTS=ROOT/'skills/paper-sketch/scripts'
sys.path.insert(0,str(SCRIPTS))
from bridge import FileBridge,write_json
from review_protocol import review_plan,validate_review,ReviewResponseError
from state import save_result,load_result,select_version,summarize_result


class ReviewPolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_schemas_reject_missing_wrong_and_contradictory_values(self):
        contract={'stage':'rewrite','fields':['critic_suggestions','revised_description']}
        for value in ('{}','[]','bad JSON','{"critic_suggestions":"Fix"}',
            '{"critic_suggestions":null,"revised_description":"Text"}',
            '{"critic_suggestions":3,"revised_description":"Text"}',
            '{"critic_suggestions":" ","revised_description":"Text"}',
            '{"critic_suggestions":"Fix","revised_description":"No changes needed."}'):
            with self.subTest(value=value),self.assertRaises(ValueError):validate_review(value,contract)
        good='```json\n{"critic_suggestions":"No changes needed.","revised_description":"No changes needed."}\n```'
        self.assertIn('No changes needed.',validate_review(good,contract))
        for value in ('not sure','NO, maybe','YES please','{}'):
            with self.assertRaises(ValueError):validate_review(value,{'stage':'gate'})

    async def test_invalid_response_gets_only_one_text_retry(self):
        for corrected in (True,False):
            with self.subTest(corrected=corrected),TemporaryDirectory() as directory:
                bridge=FileBridge(Path(directory),timeout=2)
                contract={'stage':'rewrite','fields':['critic_suggestions','revised_description']}
                with review_plan([contract]):
                    task=asyncio.create_task(bridge.call('host',[{'type':'text','text':'Original review'}],{}))
                paths=[]
                for index in range(2):
                    for _ in range(100):
                        pending=[p for p in Path(directory).glob('*/request.json') if not p.with_name('response.json').exists()]
                        if pending:break
                        await asyncio.sleep(.01)
                    path=pending[0];paths.append(path)
                    request=json.loads(path.read_text(encoding='utf-8'))
                    response='{}' if index==0 or not corrected else '{"critic_suggestions":"No changes needed.","revised_description":"No changes needed."}'
                    write_json(path.with_name('response.json'),{'id':request['id'],'text':response})
                if corrected:self.assertIn('No changes needed.',(await task)[0])
                else:
                    with self.assertRaises(ReviewResponseError):await task
                self.assertEqual(len(paths),2)
                retry=json.loads(paths[1].read_text(encoding='utf-8'))
                self.assertEqual([t['role'] for t in retry['turns']],['user','model','user'])
                self.assertEqual(retry['turns'][0]['content'][0]['text'],'Original review')
                self.assertEqual(bridge.image_calls,[])

    async def cli_case(self, root, action, outcome, *, regular_no=False, invalid_regular=False):
        """정식 CLI의 최종 검토를 실제 요청 파일과 모의 응답으로 구동."""
        root.mkdir(parents=True)
        fixture=root/'fixture.png';Image.new('RGB',(32,18),'blue').save(fixture)
        args=[sys.executable,'-B',str(SCRIPTS/'run.py'),action,'--dataset-dir',str(root),
              '--output',str(root/'out'),'--timeout','5']
        if action=='generate':
            write_json(root/'input.json',{'content':'SOURCE','visual_intent':'CAPTION'})
            args+=['--input',str(root/'input.json'),'--retrieval','none','--critic-rounds','1']
        else:
            buffer=io.BytesIO();Image.new('RGB',(32,18),'white').save(buffer,format='JPEG')
            field='target_diagram_desc0_base64_jpg'
            await save_result(root/'prior',{'content':'SOURCE','visual_intent':'CAPTION',
                'target_diagram_desc0':'HIDDEN_CURRENT_DESCRIPTION',field:base64.b64encode(buffer.getvalue()).decode(),
                'eval_image_field':field,'chat_history':[{'role':'assistant','content':'Generated.'}]})
            (root/'feedback.txt').write_text('Make encoder blue',encoding='utf-8')
            args+=['--prior',str(root/'prior/result.json'),'--feedback-file',str(root/'feedback.txt')]
        process=await asyncio.create_subprocess_exec(*args,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        records=[]
        try:
            while raw:=await asyncio.wait_for(process.stdout.readline(),timeout=15):
                line=raw.decode('utf-8').strip()
                if not line.startswith('PAPER_SKETCH_REQUEST '):continue
                path=Path(line.removeprefix('PAPER_SKETCH_REQUEST '))
                request=json.loads(path.read_text(encoding='utf-8'));records.append(request)
                response={'id':request['id']}
                if request['kind']=='image':response['image_path']=str(fixture)
                else:
                    policy=request.get('review_validation')
                    if policy is None:text='Planner description' if len(records)==1 else 'Stylist description'
                    else:
                        stage=policy['stage'];final=policy['final']
                        if final and outcome=='host_error':
                            response['error']='Simulated text host failure';text='unused'
                        elif final and outcome=='gate_failed' and stage=='gate':text='not sure'
                        elif final and outcome=='review_failed':text='{}'
                        elif not final and invalid_regular and stage == (
                                invalid_regular if isinstance(invalid_regular,str) else
                                'rewrite' if action=='generate' else 'critique'):text='{}'
                        elif stage=='context':text='{"context_diagram1":"white","context_user_turn1":"blue"}'
                        elif stage=='critique':
                            text='{"critique_latest_turn":"Inspect current figure","critique_source_content":"Inspect source","critique_presentation":"Inspect presentation"}'
                        elif stage=='gate':text='NO' if (final and outcome=='passed') or (not final and regular_no) else 'YES'
                        else:
                            no=(final and outcome=='passed') or (not final and regular_no)
                            text=json.dumps({'critic_suggestions':'No changes needed.' if no else 'Fix arrow',
                                'revised_description':'No changes needed.' if no else 'HIDDEN_REVISED_DESCRIPTION'})
                    response.update(text=text,host={'type':'independent-codex',
                        'request_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                        'response_sha256':hashlib.sha256(text.encode()).hexdigest()})
                write_json(path.with_name('response.json'),response)
            _,stderr=await process.communicate()
            return process.returncode,records,stderr.decode('utf-8')
        finally:
            if process.returncode is None:process.kill();await process.wait()

    async def test_final_three_statuses_without_extra_image_generation(self):
        for action in ('generate','refine'):
            for outcome in ('passed','issues_remaining','review_failed','gate_failed','host_error'):
                with self.subTest(action=action,outcome=outcome),TemporaryDirectory() as directory:
                    root=Path(directory)/'case'
                    code,requests,stderr=await self.cli_case(root,action,outcome)
                    self.assertEqual(code,0,stderr)
                    data=await load_result(root/'out/result.json')
                    expected='review_failed' if outcome in ('gate_failed','host_error') else outcome
                    # 최초 Critic의 결합 응답에는 별도 gate 단계가 없음
                    if action=='generate' and outcome=='gate_failed':expected='issues_remaining'
                    self.assertEqual(data['final_review']['status'],expected)
                    images=[r for r in requests if r['kind']=='image']
                    self.assertEqual(len(images),3 if action=='generate' else 1)
                    final=[r for r in requests if r.get('review_validation',{}).get('final')]
                    self.assertTrue(final)
                    self.assertTrue(all(r['kind']=='text' for r in final))
                    first_final=requests.index(final[0])
                    self.assertFalse(any(r['kind']=='image' for r in requests[first_final:]))
                    if action=='refine':
                        self.assertFalse(any(r['review_validation']['stage']=='rewrite' for r in final))
                        for request in final:
                            self.assertEqual(request['required_text_host'],'independent-codex')
                            self.assertNotIn('HIDDEN_REVISED_DESCRIPTION',json.dumps(request))
                            self.assertNotIn('HIDDEN_CURRENT_DESCRIPTION',json.dumps(request))
                    with Image.open(root/'out/final.jpg') as image:self.assertEqual(image.size,(32,18))

    async def test_regular_invalid_response_stops_with_checkpoint(self):
        for action in ('generate','refine'):
            with self.subTest(action=action),TemporaryDirectory() as directory:
                root=Path(directory)/'case'
                code,requests,stderr=await self.cli_case(root,action,'passed',invalid_regular=True)
                self.assertNotEqual(code,0)
                self.assertFalse((root/'out/result.json').exists())
                failed=json.loads((root/'out/failed_record.json').read_text(encoding='utf-8'))
                self.assertEqual(failed['final_review']['status'],'review_failed')
                bad=[r for r in requests if r.get('review_validation',{}).get('stage') in ('critique','rewrite')]
                self.assertEqual(len(bad),2)
                if action=='refine':self.assertTrue((root/'prior/final.jpg').exists())

    async def test_pb_gate_and_rewrite_invalid_responses_stop_before_image(self):
        for stage in ('gate','rewrite'):
            with self.subTest(stage=stage),TemporaryDirectory() as directory:
                root=Path(directory)/'case'
                code,requests,stderr=await self.cli_case(root,'refine','passed',invalid_regular=stage)
                self.assertNotEqual(code,0)
                self.assertFalse(any(r['kind']=='image' for r in requests))
                self.assertEqual(len([r for r in requests if r.get('review_validation',{}).get('stage')==stage]),2)
                failed=json.loads((root/'out/failed_record.json').read_text(encoding='utf-8'))
                self.assertEqual(failed['final_review']['status'],'review_failed')

    async def test_valid_no_change_review_is_reused_without_extra_calls(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)/'case'
            code,requests,stderr=await self.cli_case(root,'refine','passed',regular_no=True)
            self.assertEqual(code,0,stderr)
            data=await load_result(root/'out/result.json')
            self.assertEqual(data['final_review']['status'],'passed')
            self.assertTrue(data['final_review']['reused_existing_review'])
            self.assertEqual(len(requests),3)
            self.assertFalse(any(r['kind']=='image' for r in requests))

    async def test_selecting_another_version_does_not_inherit_final_verdict(self):
        with TemporaryDirectory() as directory:
            root=Path(directory)/'case'
            code,requests,stderr=await self.cli_case(root,'generate','passed')
            self.assertEqual(code,0,stderr)
            data=await load_result(root/'out/result.json')
            changed=dict(data)
            changed['chat_history']=data['chat_history']+[{'role':'user','content':'New requirement'},
                                                        {'role':'assistant','content':'Same image retained'}]
            changed['prior_preferred_candidates']=[data['eval_image_field']]
            self.assertEqual(summarize_result(changed)['final_review']['status'],'not_reviewed')
            selected=select_version(data,'target_diagram_desc0_base64_jpg')
            self.assertEqual(selected['final_review']['status'],'not_reviewed')
            self.assertEqual(summarize_result(selected)['final_review']['status'],'not_reviewed')
            await save_result(root/'selected',selected,action='select',parent=root/'out/result.json')
            restored=await load_result(root/'selected/result.json')
            self.assertEqual(summarize_result(restored)['final_review']['status'],'not_reviewed')
