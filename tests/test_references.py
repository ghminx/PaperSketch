import hashlib
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'skills/paper-sketch/scripts'))
from prepare_references import prepare_references


class ReferenceTests(unittest.TestCase):
    def test_corrected_copy_preserves_source_and_other_fields(self):
        from PIL import Image
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'raw'
            (source / 'images').mkdir(parents=True)
            Image.new('RGB', (8, 8), 'white').save(source / 'images/name.jpg')
            records = [{'id': 'ref_309', 'content': 'method', 'visual_intent': 'caption',
                        'path_to_gt_image': 'images/\u200cname.jpg', 'extra': {'keep': True}}]
            raw = json.dumps(records).encode()
            (source / 'ref.json').write_bytes(raw)
            target = root / 'prepared'
            result = prepare_references(source, target)
            output = json.loads((target / 'ref.json').read_text(encoding='utf-8'))
            self.assertEqual((source / 'ref.json').read_bytes(), raw)
            self.assertEqual(output[0]['extra'], records[0]['extra'])
            self.assertEqual(output[0]['content'], records[0]['content'])
            self.assertEqual(output[0]['path_to_gt_image'], 'images/name.jpg')
            self.assertEqual((target / 'images/name.jpg').read_bytes(), (source / 'images/name.jpg').read_bytes())
            self.assertEqual(len(result['corrections']), 1)
            with self.assertRaises(FileExistsError):
                prepare_references(source, target)
            with self.assertRaises(ValueError):
                prepare_references(source, source / 'nested')

    def test_missing_image_fails_without_publishing_prepared_data(self):
        with TemporaryDirectory() as directory:
            source = Path(directory) / 'raw'
            source.mkdir()
            (source / 'ref.json').write_text(json.dumps([{
                'id': 'ref_1', 'content': '', 'visual_intent': 'caption',
                'path_to_gt_image': 'images/missing.jpg'}]), encoding='utf-8')
            target = Path(directory) / 'prepared'
            with self.assertRaises(FileNotFoundError):
                prepare_references(source, target)
            self.assertFalse(target.exists())

    @unittest.skipUnless((ROOT / 'data/prepared/MTPaperBananaBench/ref.json').exists(), 'Prepared MTP dataset required')
    def test_real_prepared_data_preserves_order_and_image_bytes(self):
        source = ROOT / 'data/MTPaperBananaBench'
        target = ROOT / 'data/prepared/MTPaperBananaBench'
        original = json.loads((source / 'ref.json').read_text(encoding='utf-8'))
        prepared = json.loads((target / 'ref.json').read_text(encoding='utf-8'))
        manifest = json.loads((target / 'reference_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(len(original), 298)
        self.assertEqual([r['id'] for r in original], [r['id'] for r in prepared])
        self.assertEqual(manifest['empty_content_ids'], ['ref_260', 'ref_305'])
        self.assertEqual(manifest['source_ref_sha256'], hashlib.sha256((source / 'ref.json').read_bytes()).hexdigest())
        for before, after, image in zip(original, prepared, manifest['images']):
            expected = dict(before)
            if before['id'] == 'ref_309':
                expected['path_to_gt_image'] = before['path_to_gt_image'].replace('\u200c', '')
            self.assertEqual(after, expected)
            self.assertEqual(hashlib.sha256((target / after['path_to_gt_image']).read_bytes()).hexdigest(), image['sha256'])


if __name__ == '__main__':
    unittest.main()
