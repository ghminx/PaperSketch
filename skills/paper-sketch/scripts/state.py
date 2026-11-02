import base64
import hashlib
import io
import json
from pathlib import Path
import sys

from PIL import Image

from bridge import write_json

RUNTIME = Path(__file__).resolve().parents[1] / 'assets/interact'
sys.path.insert(0, str(RUNTIME))
from utils.base64_rw_helper import offload_base64_fields, read_base64


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
    raw = path.read_bytes()
    metadata_path = path.parent / 'state.json'
    if metadata_path.exists():
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        if hashlib.sha256(raw).hexdigest() != metadata['result_sha256']:
            raise ValueError('Result does not match state.json hash')
    data = json.loads(raw.decode('utf-8'))
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
        encoded = await read_base64(value)
        with Image.open(io.BytesIO(base64.b64decode(encoded, validate=True))) as image:
            image.verify()
        container[key] = encoded
    validate_completed_turn(data)
    return data


def summarize_result(data: dict) -> dict:
    """그림·설명·피드백·선택 가능 여부를 base64 없이 요약."""
    validate_completed_turn(data)
    current = len(data.get('prior_preferred_candidates', []))
    versions = []
    for field, value in data.items():
        if field.endswith('_base64_jpg') and value:
            selectable = current == 0 or field == data['eval_image_field'] or field.startswith(
                f'target_diagram_critic_desc{current}-')
            versions.append({'image_field': field, 'description_field': field.removesuffix('_base64_jpg'),
                             'description': data[field.removesuffix('_base64_jpg')],
                             'selected': field == data['eval_image_field'], 'selectable': selectable})
    return {'selected_field': data['eval_image_field'], 'versions': versions,
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
    return {**data, 'eval_image_field': field}


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
    stored = await offload_base64_fields(data, output)
    for container, key in _image_fields(stored):
        container[key] = Path(container[key]).relative_to(output).as_posix()
    images_dir = output / 'images'
    images_dir.mkdir()
    for index, row in enumerate(summary['versions']):
        raw = base64.b64decode(data[row['image_field']], validate=True)
        relative = f'images/{index:03d}.jpg'
        (output / relative).write_bytes(raw)
        row.update({'image': relative, 'sha256': hashlib.sha256(raw).hexdigest()})
    field = data['eval_image_field']
    (output / 'final.jpg').write_bytes(base64.b64decode(data[field], validate=True))
    (output / 'description.txt').write_text(data[field.removesuffix('_base64_jpg')], encoding='utf-8')
    write_json(output / 'result.json', stored)
    metadata = {'format_version': 1, 'action': action, **summary,
                'result_sha256': hashlib.sha256((output / 'result.json').read_bytes()).hexdigest(),
                'source_manifest_sha256': hashlib.sha256((RUNTIME / 'SOURCE_MANIFEST.json').read_bytes()).hexdigest()}
    if parent is not None:
        metadata['parent'] = {'path': str(parent.resolve()), 'sha256': hashlib.sha256(parent.read_bytes()).hexdigest()}
    write_json(output / 'state.json', metadata)
