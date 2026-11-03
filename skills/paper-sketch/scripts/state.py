import base64
import hashlib
import io
import json
from pathlib import Path
import sys

from PIL import Image

from bridge import write_json
from image_ratio import assess_ratio
from review_protocol import context_hash

RUNTIME = Path(__file__).resolve().parents[1] / 'assets/interact'
sys.path.insert(0, str(RUNTIME))
from utils.base64_rw_helper import offload_base64_fields


def _image_fields(value):
    """원본 offload와 같은 규칙으로 중첩 이미지 필드 순회."""
    if isinstance(value, dict):
        for key, item in value.items():
            if 'base64' in key and isinstance(item, str) and item:
                yield value, key
            else:
                yield from _image_fields(item)
    elif isinstance(value, list):
        for item in value:
            yield from _image_fields(item)


def _read_blob(path: Path) -> str:
    """원본 base64 문자열의 UTF-8 hash와 blob 파일명 일치 확인."""
    name = path.name
    if len(name) != 64 or any(c not in '0123456789abcdef' for c in name):
        raise ValueError(f'Expected a content-addressed blob name: {path}')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != name:
        raise ValueError(f'Blob content hash mismatch: {path}')
    return raw.decode('utf-8')


async def _store_images(data: dict, output: Path) -> dict:
    """원본 저장 helper 재사용 후 기존 blob까지 재검증하고 상대 경로 반환."""
    stored = await offload_base64_fields(data, output)
    for container, key in _image_fields(stored):
        blob = Path(container[key])
        _read_blob(blob)
        container[key] = blob.relative_to(output).as_posix()
    return stored


def _verify_exports(root: Path, data: dict, metadata: dict):
    """선택·버전별 이미지·내보낸 설명과 복원 record의 일치 확인."""
    summary = summarize_result(data)
    for key in ('image_ratios', 'selected_image_ratio', 'final_review', 'execution'):
        if key in metadata and metadata[key] != summary[key]:
            raise ValueError(f'{key} metadata does not match the record')
    if metadata['selected_field'] != summary['selected_field']:
        raise ValueError('Selected field does not match state.json')
    versions = {row['image_field']: row for row in metadata['versions']}
    if len(versions) != len(metadata['versions']) or set(versions) != {
            row['image_field'] for row in summary['versions']}:
        raise ValueError('Version fields do not match state.json')
    for expected in summary['versions']:
        row = versions[expected['image_field']]
        if any(row[key] != expected[key] for key in expected):
            raise ValueError(f'Version metadata mismatch: {expected["image_field"]}')
        raw = base64.b64decode(data[row['image_field']], validate=True)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != row['sha256']:
            raise ValueError(f'Version image hash mismatch: {row["image_field"]}')
        exported = (root / row['image']).resolve()
        if not exported.is_relative_to(root / 'images'):
            raise ValueError('Export path escapes the images directory')
        if hashlib.sha256(exported.read_bytes()).hexdigest() != digest:
            raise ValueError(f'Export image hash mismatch: {row["image"]}')
    selected = versions[data['eval_image_field']]
    if hashlib.sha256((root / 'final.jpg').read_bytes()).hexdigest() != selected['sha256']:
        raise ValueError('Selected final.jpg hash mismatch')
    description = data[selected['description_field']].replace('\r\n', '\n').replace('\r', '\n')
    if (root / 'description.txt').read_text(encoding='utf-8') != description:
        raise ValueError('Selected description.txt does not match the record')


def validate_completed_turn(data: dict):
    """이전 그림 key와 완료 대화 턴의 일대일 대응 확인."""
    history = data['chat_history']
    count = len(data.get('prior_preferred_candidates', []))
    expected = ['assistant'] + ['user', 'assistant'] * count
    if [turn['role'] for turn in history] != expected:
        raise ValueError('Input is not a completed PaperSketch turn')
    for field in [*data.get('prior_preferred_candidates', []), data['eval_image_field']]:
        if not data[field]:
            raise ValueError(f'Missing history image: {field}')


async def load_result(path: Path) -> dict:
    """상대 blob·원본 절대 blob·이전 inline 결과를 원본 입력으로 복원.

    Returns:
        모든 base64 필드가 inline 문자열로 복원된 완료 턴 record.
    """
    path = path.resolve()
    if (path.parent / 'failure.json').exists():
        raise ValueError('A failed run cannot be resumed as a completed result; use the prior completed run')
    raw = path.read_bytes()
    metadata_path = path.parent / 'state.json'
    metadata = None
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if hashlib.sha256(raw).hexdigest() != metadata['result_sha256']:
            raise ValueError('Result does not match state.json hash')
    data = json.loads(raw.decode('utf-8'))
    if metadata is None and any(container[key].startswith('base64/') for container, key in _image_fields(data)):
        raise FileNotFoundError(f'Missing state.json for a PaperSketch result: {metadata_path}')
    for container, key in _image_fields(data):
        value = container[key]
        if value.startswith('base64/'):
            blob = (path.parent / value).resolve()
            if not blob.is_relative_to(path.parent / 'base64'):
                raise ValueError('Blob path escapes the result directory')
            if not blob.is_file():
                raise FileNotFoundError(blob)
            value = str(blob)
        elif Path(value).is_absolute() and not Path(value).is_file():
            raise FileNotFoundError(value)
        encoded = _read_blob(Path(value)) if Path(value).is_absolute() else value
        with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as image:
            image.verify()
        container[key] = encoded
    validate_completed_turn(data)
    if metadata is not None:
        _verify_exports(path.parent, data, metadata)
    return data


def summarize_result(data: dict) -> dict:
    """그림·설명·피드백·선택 가능 여부를 base64 없이 요약."""
    validate_completed_turn(data)
    current = len(data.get('prior_preferred_candidates', []))
    versions = []
    ratios = {}
    requested = data.get('requested_image_ratio', data.get('additional_info', {}).get('rounded_ratio'))
    for field, value in data.items():
        if field.endswith('_base64_jpg') and value:
            selectable = current == 0 or field == data['eval_image_field'] or field.startswith(
                f'target_diagram_critic_desc{current}-')
            versions.append({'image_field': field, 'description_field': field.removesuffix('_base64_jpg'),
                             'description': data[field.removesuffix('_base64_jpg')],
                             'selected': field == data['eval_image_field'], 'selectable': selectable})
            with Image.open(io.BytesIO(base64.b64decode(value, validate=True))) as image:
                ratios[field] = assess_ratio(*image.size, requested)
    selected = data['eval_image_field']
    review = data.get('final_review')
    digest = hashlib.sha256(base64.b64decode(data[selected], validate=True)).hexdigest()
    if review is None or any(review.get(k) != v for k, v in {
            'image_field': selected, 'image_sha256': digest, 'context_sha256': context_hash(data)}.items()):
        review = {'status': 'not_reviewed', 'reason': 'No final review for the selected image and requirements'}
    return {'selected_field': selected, 'versions': versions, 'final_review': review,
            'execution': data.get('execution_record', {'status': 'unverified',
                'reason': 'No execution record in this legacy result'}),
            'image_ratios': ratios, 'selected_image_ratio': ratios[data['eval_image_field']],
            'image_generation_status': data.get('image_generation_status', 'complete'),
            'image_generation_history': data.get('image_generation_history', []),
            'feedback': [t['content'] for t in data['chat_history'] if t['role'] == 'user'],
            'prior_preferred_candidates': data.get('prior_preferred_candidates', [])}


def select_version(data: dict, field: str) -> dict:
    """완료된 현재 턴의 그림 선택을 별도 record에 반영."""
    versions = summarize_result(data)['versions']
    match = next((row for row in versions if row['image_field'] == field), None)
    if match is None:
        raise ValueError(f'Unknown image field: {field}')
    if not match['selectable']:
        raise ValueError('To branch from an earlier turn, use that turn\'s result.json')
    selected = {**data, 'eval_image_field': field}
    review = data.get('final_review')
    if review is not None and review.get('image_field') != field:
        selected['review_history'] = [*data.get('review_history', []), review]
        selected['final_review'] = {'status': 'not_reviewed', 'image_field': field,
            'image_sha256': hashlib.sha256(base64.b64decode(data[field], validate=True)).hexdigest(),
            'context_sha256': context_hash(data), 'reason': 'Selected version changed; final review required'}
    return selected


async def save_result(output: Path, data: dict, *, action='generate', parent: Path | None = None):
    """원본 content-addressed 저장을 재사용한 이동 가능한 완료 결과 저장.

    원본 blob 경로만 저장 경계에서 상대 경로로 변환하며,
    load_result에서 다시 inline 원본 계약으로 복원하는 방식.
    """
    output = output.resolve()
    if (output / 'result.json').exists() or (output / 'state.json').exists():
        raise FileExistsError(f'Use a new output directory: {output}')
    summary = summarize_result(data)
    for container, key in _image_fields(data):
        with Image.open(io.BytesIO(base64.b64decode(container[key], validate=True))) as image:
            image.verify()
    output.mkdir(parents=True, exist_ok=True)
    stored = await _store_images(data, output)
    images_dir = output / 'images'
    images_dir.mkdir()
    for index, row in enumerate(summary['versions']):
        raw = base64.b64decode(data[row['image_field']], validate=True)
        relative = f'images/{index:03d}.jpg'
        (output / relative).write_bytes(raw)
        row.update({'image': relative, 'sha256': hashlib.sha256(raw).hexdigest()})
    field = data['eval_image_field']
    (output / 'final.jpg').write_bytes(base64.b64decode(data[field], validate=True))
    (output / 'description.txt').write_text(data[field.removesuffix('_base64_jpg')], encoding='utf-8', newline='')
    write_json(output / 'result.json', stored)
    metadata = {'format_version': 1, 'action': action, **summary,
                'result_sha256': hashlib.sha256((output / 'result.json').read_bytes()).hexdigest(),
                'source_manifest_sha256': hashlib.sha256((RUNTIME / 'SOURCE_MANIFEST.json').read_bytes()).hexdigest()}
    if parent is not None:
        metadata['parent'] = {'path': str(parent.resolve()), 'sha256': hashlib.sha256(parent.read_bytes()).hexdigest()}
    _verify_exports(output, data, metadata)
    write_json(output / 'state.json', metadata)


async def save_failed_result(output: Path, data: dict, error: Exception):
    """완료 결과와 구분되는 실패 기록·중간 설명·그림 보존."""
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stored = await _store_images(data, output)
    write_json(output / 'failed_record.json', stored)
    write_json(output / 'failure.json', {'status': 'failed', 'error_type': type(error).__name__,
               'error': str(error), 'record': 'failed_record.json', 'resumable_as_completed': False})
