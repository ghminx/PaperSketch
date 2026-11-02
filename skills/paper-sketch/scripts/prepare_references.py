import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil

from PIL import Image

from bridge import write_json


def prepare_references(source: Path, destination: Path) -> dict:
    """원본을 보존한 채 원본 agent가 읽을 참고 데이터 사본 생성.

    Args:
        source: 다운로드한 MTPaperBananaBench root.
        destination: 새 실행용 root. ref.json·images·manifest 생성 위치.

    Returns:
        원본 hash, 경로 보정, 빈 본문 및 이미지 검증 기록.
    """
    source, destination = source.resolve(), destination.resolve()
    if destination == source or source in destination.parents:
        raise ValueError('Prepared data must be outside the original dataset')
    if destination.exists():
        raise FileExistsError(f'Use a new prepared directory: {destination}')
    raw = (source / 'ref.json').read_bytes()
    records = json.loads(raw)
    ids = [r['id'] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate reference IDs')
    prepared = copy.deepcopy(records)
    entries, corrections = [], []
    for record in prepared:
        for key in ('id', 'content', 'visual_intent', 'path_to_gt_image'):
            record[key]
        original_path = record['path_to_gt_image']
        relative = Path(original_path)
        path = (source / relative).resolve()
        if not path.is_relative_to(source):
            raise ValueError(f'Reference path leaves dataset: {record["id"]}')
        if not path.is_file() and record['id'] == 'ref_309' and relative.name.startswith('\u200c'):
            relative = relative.with_name(relative.name.removeprefix('\u200c'))
            path = source / relative
            record['path_to_gt_image'] = relative.as_posix()
            corrections.append({'id': record['id'], 'original_path': original_path,
                                'prepared_path': relative.as_posix(), 'reason': 'leading U+200C filename mismatch'})
        with Image.open(path) as image:
            image.verify()
        entries.append({'id': record['id'], 'source_path': str(path),
                        'prepared_path': relative.as_posix(),
                        'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    destination.mkdir(parents=True)
    for entry in entries:
        target = destination / entry['prepared_path']
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(entry['source_path'], target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != entry['sha256']:
            raise OSError(f'Copied image differs: {entry["id"]}')
    write_json(destination / 'ref.json', prepared)
    manifest = {'source': str(source), 'source_ref_sha256': hashlib.sha256(raw).hexdigest(),
                'records': len(records), 'images_verified': len(entries),
                'empty_content_ids': [r['id'] for r in records if not r['content']],
                'corrections': corrections, 'images': entries}
    if (source / 'ref.json').read_bytes() != raw:
        raise OSError('Original reference JSON changed during preparation')
    write_json(destination / 'reference_manifest.json', manifest)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = prepare_references(args.source, args.output)
    print(json.dumps({key: value for key, value in manifest.items() if key != 'images'}, ensure_ascii=True))
