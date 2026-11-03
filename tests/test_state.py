import base64
import asyncio
import copy
import io
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/paper-sketch/scripts'))
from state import load_result, save_result, select_version, summarize_result


class StateTests(unittest.IsolatedAsyncioTestCase):
    def record(self):
        buffer = io.BytesIO()
        Image.new('RGB', (32, 18), 'white').save(buffer, format='JPEG')
        image = base64.b64encode(buffer.getvalue()).decode()
        return {'content': 'SOURCE', 'visual_intent': 'CAPTION',
                'target_diagram_desc0': 'Planner description.',
                'target_diagram_desc0_base64_jpg': image,
                'target_diagram_stylist_desc0': 'Stylist description.',
                'target_diagram_stylist_desc0_base64_jpg': image,
                'eval_image_field': 'target_diagram_stylist_desc0_base64_jpg',
                'chat_history': [{'role': 'assistant', 'content': 'Generated.'}]}

    async def test_upstream_offload_deduplicates_and_relocated_result_is_complete(self):
        """원본 blob 저장·중복 제거와 폴더 이동 후 중첩 record 복원 확인."""
        data = self.record()
        data['unpreferred_candidates'] = [{'other_base64_jpg': data['target_diagram_desc0_base64_jpg']}]
        before = copy.deepcopy(data)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / 'original'
            await save_result(output, data, action='generate')
            self.assertEqual(data, before)
            stored = json.loads((output / 'result.json').read_text(encoding='utf-8'))
            self.assertTrue(stored['target_diagram_desc0_base64_jpg'].startswith('base64/'))
            self.assertEqual(len(list((output / 'base64').iterdir())), 1)
            output.rename(root / 'moved')
            moved = root / 'moved'
            self.assertEqual(await load_result(moved / 'result.json'), before)
            self.assertEqual((moved / 'description.txt').read_text(encoding='utf-8'), 'Stylist description.')
            self.assertEqual((moved / 'final.jpg').read_bytes(), base64.b64decode(before[before['eval_image_field']]))
            with self.assertRaises(FileExistsError):
                await save_result(moved, data, action='generate')

    async def test_current_turn_selection_and_old_turn_rejection(self):
        """같은 턴 선택과 과거 턴·현재 이력 혼합 차단 확인."""
        data = self.record()
        selected = select_version(data, 'target_diagram_desc0_base64_jpg')
        self.assertEqual(selected['eval_image_field'], 'target_diagram_desc0_base64_jpg')
        self.assertEqual(data['eval_image_field'], 'target_diagram_stylist_desc0_base64_jpg')
        refined = copy.deepcopy(data)
        refined.update({'current_critic_round': [1, 0],
                        'prior_preferred_candidates': [data['eval_image_field']],
                        'target_diagram_critic_desc1-0': 'Revised.',
                        'target_diagram_critic_desc1-0_base64_jpg': data[data['eval_image_field']],
                        'eval_image_field': 'target_diagram_critic_desc1-0_base64_jpg',
                        'chat_history': data['chat_history'] + [
                            {'role': 'user', 'content': 'Change color.'},
                            {'role': 'assistant', 'content': 'Revised.'}]})
        with self.assertRaisesRegex(ValueError, 'earlier turn'):
            select_version(refined, 'target_diagram_desc0_base64_jpg')
        summary = summarize_result(refined)
        self.assertEqual(summary['selected_field'], refined['eval_image_field'])
        self.assertEqual(summary['feedback'], ['Change color.'])
        self.assertEqual(sum(row['selectable'] for row in summary['versions']), 1)

    async def test_missing_blob_and_invalid_image_fail_explicitly(self):
        """누락 저장 파일·잘못된 이미지의 성공 복원 방지 확인."""
        with TemporaryDirectory() as directory:
            output = Path(directory)
            data = self.record()
            await save_result(output, data, action='generate')
            next((output / 'base64').iterdir()).unlink()
            with self.assertRaises(FileNotFoundError):
                await load_result(output / 'result.json')
        with TemporaryDirectory() as directory:
            data = self.record()
            data[data['eval_image_field']] = base64.b64encode(b'not-an-image').decode()
            with self.assertRaises(OSError):
                await save_result(Path(directory), data, action='generate')
            self.assertFalse((Path(directory) / 'result.json').exists())

    async def test_cli_inspect_select_and_self_contained_branch(self):
        """모델 호출 없는 조회·선택 CLI와 이전 출력 보존 확인."""
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prior = root / 'prior'
            data = self.record()
            blue = io.BytesIO()
            Image.new('RGB', (32, 18), 'blue').save(blue, format='JPEG')
            data['target_diagram_desc0_base64_jpg'] = base64.b64encode(blue.getvalue()).decode()
            await save_result(prior, data, action='generate')
            original = (prior / 'result.json').read_bytes()
            script = str(ROOT / 'skills/paper-sketch/scripts/run.py')
            inspect = subprocess.run([sys.executable, script, 'inspect', '--prior', str(prior / 'result.json')],
                                     capture_output=True, text=True, timeout=10)
            self.assertEqual(inspect.returncode, 0, inspect.stderr)
            self.assertEqual(json.loads(inspect.stdout)['selected_field'], self.record()['eval_image_field'])
            output = root / 'selection'
            command = [sys.executable, script, 'select', '--prior', str(prior / 'result.json'),
                       '--image-field', 'target_diagram_desc0_base64_jpg', '--output', str(output)]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((output / 'requests').exists())
            self.assertEqual((prior / 'result.json').read_bytes(), original)
            shutil.copytree(output, root / 'moved')
            selected = await load_result(root / 'moved/result.json')
            self.assertEqual(selected['eval_image_field'], 'target_diagram_desc0_base64_jpg')
            self.assertEqual((output / 'final.jpg').read_bytes(), blue.getvalue())
            metadata = json.loads((output / 'state.json').read_text(encoding='utf-8'))
            self.assertEqual(metadata['action'], 'select')
            self.assertIn('sha256', metadata['parent'])
            failure = subprocess.run(command, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(failure.returncode, 0)

    async def test_legacy_inline_absolute_blobs_and_metadata_mismatch(self):
        """이전 inline·원본 절대 blob 지원과 결과 변조 감지 확인."""
        from utils.base64_rw_helper import offload_base64_fields
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.record()
            inline = root / 'inline.json'
            inline.write_text(json.dumps(data), encoding='utf-8')
            self.assertEqual(await load_result(inline), data)
            legacy = await offload_base64_fields(data, root)
            absolute = root / 'absolute.json'
            absolute.write_text(json.dumps(legacy), encoding='utf-8')
            self.assertEqual(await load_result(absolute), data)
            output = root / 'new'
            await save_result(output, data, action='generate')
            (output / 'result.json').write_text(json.dumps(data), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash'):
                await load_result(output / 'result.json')

    def different_image(self):
        """다른 정상 이미지로의 교체 시험용 JPEG 구성."""
        buffer = io.BytesIO()
        Image.new('RGB', (32,18), 'red').save(buffer,format='JPEG')
        return buffer.getvalue()

    async def test_blob_replacement_corruption_and_missing_are_detected(self):
        for mode in ('replace', 'corrupt', 'missing'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                output = Path(directory)
                await save_result(output, self.record())
                blob = next((output/'base64').iterdir())
                final = (output/'final.jpg').read_bytes()
                if mode=='replace':
                    blob.write_text(base64.b64encode(self.different_image()).decode(),encoding='utf-8')
                elif mode=='corrupt':
                    blob.write_bytes(b'broken blob')
                else:
                    blob.unlink()
                expected = FileNotFoundError if mode=='missing' else ValueError
                with self.assertRaises(expected):
                    await load_result(output/'result.json')
                self.assertEqual((output/'final.jpg').read_bytes(), final)

    async def test_nested_history_blob_is_verified(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            data = self.record()
            data['unpreferred_candidates'] = [{'old_base64_jpg':base64.b64encode(self.different_image()).decode()}]
            await save_result(output,data)
            stored = json.loads((output/'result.json').read_text(encoding='utf-8'))
            blob = output/stored['unpreferred_candidates'][0]['old_base64_jpg']
            blob.write_text(data['target_diagram_desc0_base64_jpg'],encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Blob content hash'):
                await load_result(output/'result.json')

    async def test_viewable_exports_must_match_the_selected_record(self):
        for mode in ('final_replace','version_replace','description_replace','final_missing','version_missing',
                     'description_missing','state_missing'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                output = Path(directory)
                await save_result(output,self.record())
                if mode=='final_replace': (output/'final.jpg').write_bytes(self.different_image())
                if mode=='version_replace': (output/'images/000.jpg').write_bytes(self.different_image())
                if mode=='description_replace': (output/'description.txt').write_text('Other description',encoding='utf-8')
                if mode=='final_missing': (output/'final.jpg').unlink()
                if mode=='version_missing': (output/'images/000.jpg').unlink()
                if mode=='description_missing': (output/'description.txt').unlink()
                if mode=='state_missing': (output/'state.json').unlink()
                with self.assertRaises((ValueError,FileNotFoundError)):
                    await load_result(output/'result.json')

    async def test_selected_version_metadata_cannot_silently_change(self):
        for mode in ('selection','image_hash','description','duplicate_version'):
            with self.subTest(mode=mode), TemporaryDirectory() as directory:
                output = Path(directory)
                await save_result(output,self.record())
                path = output/'state.json'
                metadata = json.loads(path.read_text(encoding='utf-8'))
                if mode=='selection': metadata['selected_field']='target_diagram_desc0_base64_jpg'
                if mode=='image_hash': metadata['versions'][0]['sha256']='0'*64
                if mode=='description': metadata['versions'][0]['description']='Other description'
                if mode=='duplicate_version': metadata['versions'].append(metadata['versions'][0])
                path.write_text(json.dumps(metadata),encoding='utf-8')
                with self.assertRaises(ValueError): await load_result(output/'result.json')

    async def test_save_rejects_existing_wrong_blob_without_overwriting_it(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            data = self.record()
            encoded = data[data['eval_image_field']]
            blob = output/'base64'/hashlib.sha256(encoded.encode()).hexdigest()
            blob.parent.mkdir()
            replacement = base64.b64encode(self.different_image()).decode().encode()
            blob.write_bytes(replacement)
            with self.assertRaisesRegex(ValueError,'Blob content hash'):
                await save_result(output,data)
            self.assertEqual(blob.read_bytes(),replacement)
            self.assertFalse((output/'result.json').exists())

    async def test_legacy_absolute_blob_replacement_is_detected(self):
        from utils.base64_rw_helper import offload_base64_fields
        with TemporaryDirectory() as directory:
            output = Path(directory)
            stored = await offload_base64_fields(self.record(),output)
            record = output/'absolute.json'
            record.write_text(json.dumps(stored),encoding='utf-8')
            blob = Path(stored[stored['eval_image_field']])
            blob.write_text(base64.b64encode(self.different_image()).decode(),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Blob content hash'):
                await load_result(record)

    async def test_tampered_blob_blocks_refine_before_any_model_request(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            prior = root/'prior'
            await save_result(prior,self.record())
            next((prior/'base64').iterdir()).write_text(
                base64.b64encode(self.different_image()).decode(),encoding='utf-8')
            feedback = root/'feedback.txt'
            feedback.write_text('Change the encoder',encoding='utf-8')
            process = await asyncio.create_subprocess_exec(sys.executable,'-B',str(ROOT/'skills/paper-sketch/scripts/run.py'),
                'refine','--prior',str(prior/'result.json'),'--feedback-file',str(feedback),
                '--dataset-dir',str(root),'--output',str(root/'next'),
                stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
            stdout,stderr = await asyncio.wait_for(process.communicate(),timeout=15)
            self.assertNotEqual(process.returncode,0)
            self.assertNotIn(b'PAPER_SKETCH_REQUEST',stdout)
            self.assertIn(b'Blob content hash',stderr)

    async def test_description_newlines_survive_save_load(self):
        with TemporaryDirectory() as directory:
            output=Path(directory)
            data=self.record()
            data['target_diagram_stylist_desc0']='First\r\nSecond\nThird'
            await save_result(output,data)
            self.assertEqual(await load_result(output/'result.json'),data)


if __name__ == '__main__':
    unittest.main()
