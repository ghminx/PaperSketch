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
sys.path.insert(0,str(ROOT/'skills/paper-sketch/scripts'))
from bridge import FileBridge,write_json
from image_ratio import assess_ratio
from state import load_result,save_result,select_version,summarize_result


class ImageRatioTests(unittest.IsolatedAsyncioTestCase):
    def test_ratio_measurements_and_explicit_tolerance(self):
        self.assertEqual(assess_ratio(210,90,'21:9')['status'],'exact')
        self.assertEqual(assess_ratio(100,100,'1:1')['status'],'exact')
        self.assertEqual(assess_ratio(90,160,'9:16')['status'],'exact')
        rounded=assess_ratio(1672,941,'16:9')
        self.assertEqual(rounded['status'],'within_tolerance')
        self.assertFalse(rounded['exact_match'])
        mismatch=assess_ratio(1672,941,'21:9')
        self.assertEqual(mismatch['status'],'mismatch')
        self.assertGreater(mismatch['relative_error'],0.23)
        self.assertEqual(assess_ratio(100,100,None)['status'],'not_requested')
        for bad in ('0:9','-1:9','16x9','16:0'):
            with self.assertRaises(ValueError):assess_ratio(100,100,bad)

    async def test_bridge_mismatch_is_successful_without_retry_or_pixel_changes(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);path=root/'fixture.png'
            Image.new('RGB',(160,90),'blue').save(path)
            before=path.read_bytes()
            bridge=FileBridge(root/'requests',timeout=2)
            task=asyncio.create_task(bridge.call('image', [{'type':'text','text':'Full original description'}],
                {'response_modalities':['IMAGE'],'image_config':{'aspect_ratio':'21:9'}},max_attempts=5,retry_delay=0))
            await asyncio.sleep(.02)
            request_path=next((root/'requests').glob('*/request.json'))
            request=json.loads(request_path.read_text(encoding='utf-8'))
            write_json(request_path.with_name('response.json'),{'id':request['id'],'image_path':str(path)})
            result=await task
            self.assertEqual(base64.b64decode(result[0]),before)
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(len(bridge.image_calls[0]['attempts']),1)
            self.assertEqual(bridge.image_calls[0]['status'],'succeeded')
            outcome=json.loads(request_path.with_name('outcome.json').read_text(encoding='utf-8'))
            self.assertEqual(outcome['image_ratio']['status'],'mismatch')
            self.assertIn('21:9',outcome['image_ratio']['warning'])

    def record(self):
        images=[]
        for size in [(210,90),(160,90)]:
            buffer=io.BytesIO();Image.new('RGB',size,'white').save(buffer,format='JPEG')
            images.append(base64.b64encode(buffer.getvalue()).decode())
        return {'content':'SOURCE','visual_intent':'CAPTION',
            'additional_info':{'rounded_ratio':'21:9'},
            'target_diagram_desc0':'Wide plan','target_diagram_desc0_base64_jpg':images[0],
            'target_diagram_stylist_desc0':'Other render','target_diagram_stylist_desc0_base64_jpg':images[1],
            'eval_image_field':'target_diagram_stylist_desc0_base64_jpg',
            'chat_history':[{'role':'assistant','content':'Generated.'}]}

    async def test_saved_ratio_and_selected_version_follow_original_bytes(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);data=self.record()
            await save_result(root/'prior',data)
            restored=await load_result(root/'prior/result.json')
            self.assertEqual(restored,data)
            metadata=json.loads((root/'prior/state.json').read_text(encoding='utf-8'))
            self.assertEqual(metadata['selected_image_ratio']['status'],'mismatch')
            before=(root/'prior/final.jpg').read_bytes()
            selected=select_version(restored,'target_diagram_desc0_base64_jpg')
            await save_result(root/'selected',selected,action='select',parent=root/'prior/result.json')
            summary=summarize_result(await load_result(root/'selected/result.json'))
            self.assertEqual(summary['selected_image_ratio']['status'],'exact')
            self.assertEqual((root/'selected/final.jpg').read_bytes(),base64.b64decode(data['target_diagram_desc0_base64_jpg']))
            self.assertEqual((root/'prior/final.jpg').read_bytes(),before)

    async def test_older_metadata_is_read_without_changing_image_or_files(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);data=self.record()
            await save_result(root,data)
            path=root/'state.json';metadata=json.loads(path.read_text(encoding='utf-8'))
            del metadata['image_ratios'];del metadata['selected_image_ratio']
            path.write_text(json.dumps(metadata),encoding='utf-8')
            before=hashlib.sha256((root/'final.jpg').read_bytes()).hexdigest()
            self.assertEqual((await load_result(root/'result.json')),data)
            self.assertEqual(summarize_result(data)['selected_image_ratio']['status'],'mismatch')
            self.assertEqual(hashlib.sha256((root/'final.jpg').read_bytes()).hexdigest(),before)

    async def test_real_generate_cli_reports_mismatch_and_keeps_dimensions(self):
        import test_image_recovery as recovery
        with TemporaryDirectory() as directory:
            root=Path(directory);image=root/'fixture.png'
            Image.new('RGB',(1672,941),'white').save(image)
            before=image.read_bytes()
            code,output,stdout,stderr=await recovery.ImageRecoveryTests().cli(root,'generate',[
                {'image_path':str(image)},{'image_path':str(image)}])
            self.assertEqual(code,0,stderr)
            final=json.loads(stdout.splitlines()[-1])
            self.assertEqual(final['status'],'complete')
            self.assertEqual(final['selected_image_ratio']['status'],'mismatch')
            self.assertIn('PAPER_SKETCH_RATIO_WARNING',stdout)
            self.assertEqual(image.read_bytes(),before)
            with Image.open(output/'final.jpg') as exported:self.assertEqual(exported.size,(1672,941))
            saved=await load_result(output/'result.json')
            self.assertEqual(saved['requested_image_ratio'],'21:9')
            self.assertEqual(saved['image_generation_status'],'complete')
