import asyncio
import base64
import json
from pathlib import Path
import sys
from types import ModuleType
import uuid


def write_json(path: Path, payload: dict | list) -> None:
    """읽는 쪽의 부분 파일 노출을 방지하는 JSON 저장."""
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


class FileBridge:
    """원본의 모델 호출을 host가 처리할 요청·응답 파일로 연결."""

    def __init__(self, directory: Path, timeout: float = 300):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout

    def _turn(self, value, directory: Path) -> dict:
        if isinstance(value, list):
            role, parts = 'user', value
        else:
            role, parts = value.role, value.parts
        content = []
        for part in parts:
            if isinstance(part, dict):
                if part['type'] == 'text':
                    content.append({'type': 'text', 'text': part['text']})
                    continue
                if part['type'] != 'image':
                    raise ValueError(f'Unsupported input part: {part["type"]}')
                if 'image_base64' in part:
                    encoded, mime = part['image_base64'], 'image/jpeg'
                else:
                    source = part['source']
                    if source['type'] != 'base64':
                        raise ValueError('Only base64 image input is supported')
                    encoded, mime = source['data'], source['media_type']
                raw = base64.b64decode(encoded, validate=True)
            elif part.text is not None:
                content.append({'type': 'text', 'text': part.text})
                continue
            elif part.inline_data is not None:
                raw, mime = part.inline_data.data, part.inline_data.mime_type
            else:
                raise ValueError('Unsupported SDK content part')
            path = directory / f'input-{uuid.uuid4().hex}.image'
            path.write_bytes(raw)
            content.append({'type': 'image', 'path': str(path), 'media_type': mime})
        return {'role': role, 'content': content}

    async def call(self, model_name, contents, config, *, multiturn_input=False,
                   return_content=False, **retry_options):
        """텍스트는 list[str], 이미지는 base64 list로 반환.

        Args:
            contents: 원본 generic content 또는 Gemini Content로 구성된 입력.
            config: 원본 GenerateContentConfig 또는 dict 설정.
            multiturn_input: model 역할을 포함한 다중 턴 입력 여부.

        Returns:
            원본 agent에서 처리할 단일 응답 목록.
        """
        if return_content:
            raise ValueError('The host bridge does not support return_content')
        settings = config if isinstance(config, dict) else config.model_dump(mode='json', exclude_none=True)
        if settings.get('candidate_count', 1) != 1:
            raise ValueError('The host bridge supports one candidate per request')
        modalities = settings.get('response_modalities', [])
        kind = 'image' if 'IMAGE' in modalities else 'text'
        request_id = uuid.uuid4().hex
        directory = self.directory / request_id
        directory.mkdir()
        turns = contents if multiturn_input else [contents]
        request = {'id': request_id, 'kind': kind, 'model_name': model_name,
                   'config': settings, 'retry_options': retry_options,
                   'turns': [self._turn(turn, directory) for turn in turns]}
        write_json(directory / 'request.json', request)
        print(f'PAPER_SKETCH_REQUEST {directory / "request.json"}', flush=True)
        response_path = directory / 'response.json'
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        while not response_path.exists():
            if loop.time() >= deadline:
                raise TimeoutError(f'Host response not received: {directory}')
            await asyncio.sleep(0.1)
        response = json.loads(response_path.read_text(encoding='utf-8'))
        if response['id'] != request_id:
            raise ValueError('Response ID does not match request')
        if 'error' in response:
            raise RuntimeError(response['error'])
        if kind == 'text':
            result = response['text']
            if not isinstance(result, str) or not result.strip():
                raise ValueError('A non-empty text response is required')
            return [result]
        from PIL import Image
        path = Path(response['image_path'])
        if not path.is_absolute():
            raise ValueError('image_path must be absolute')
        with Image.open(path) as image:
            image.verify()
        return [base64.b64encode(path.read_bytes()).decode('ascii')]


def install_bridge(bridge: FileBridge) -> None:
    """provider 모듈의 import 시 인증 탐색 없이 호출 경계 교체.

    원본 agent를 import하기 전에 한 번 호출할 필요가 있음.
    """
    name = 'utils.generation_utils'
    if name in sys.modules:
        raise RuntimeError('Install the bridge before importing upstream agents')
    module = ModuleType(name)
    module.call_model_with_retry_async = bridge.call
    module.call_gemini_with_retry_async = bridge.call
    module.call_claude_with_retry_async = unsupported_provider
    module.call_openai_with_retry_async = unsupported_provider
    module.provider_key = lambda provider: ''
    sys.modules[name] = module
    runtime = Path(__file__).resolve().parents[1] / 'assets' / 'interact'
    sys.path.insert(0, str(runtime))


async def unsupported_provider(*args, **kwargs):
    """원본 평가기의 외부 provider 호출에 대한 명시적 실패."""
    raise RuntimeError('External provider evaluation is not enabled; use the Codex host bridge')
