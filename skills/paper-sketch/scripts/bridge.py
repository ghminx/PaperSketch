import asyncio
import base64
import json
import hashlib
import io
from pathlib import Path
import sys
from types import ModuleType
import uuid

from image_ratio import assess_ratio, canvas_instruction
from review_protocol import REVIEW_PLAN, ReviewDecision, ReviewResponseError, validate_review


def write_json(path: Path, payload: dict | list) -> None:
    """읽는 쪽의 부분 파일 노출을 방지하는 JSON 저장."""
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


class FileBridge:
    """원본의 모델 호출을 host가 처리할 요청·응답 파일로 연결."""

    def __init__(self, directory: Path, timeout: float = 300, *, independent_text: bool = False):
        self.directory = directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
        self.independent_text = independent_text
        self.canvas_ratio = None
        self.image_calls = []
        self.image_blocked = None
        self.review_calls = []
        self.request_paths = []

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
        if kind == 'image':
            return await self._image(model_name, contents, settings, multiturn_input, retry_options)
        plan = REVIEW_PLAN.get()
        contract = next(plan) if plan is not None else None
        if contract is not None:
            try:
                return await self._review_text(model_name, contents, settings, multiturn_input, retry_options, contract)
            except ReviewDecision:
                raise
            except Exception as error:
                self.review_calls[-1].update(status='review_failed', error=str(error))
                write_json(self.directory / 'review_validation.json', self.review_calls)
                raise
        directory, response = await self._exchange(model_name, contents, settings, multiturn_input, retry_options)
        if 'error' in response:
            raise RuntimeError(response['error'])
        result = response['text']
        if not isinstance(result, str) or not result.strip():
            raise ValueError('A non-empty text response is required')
        if self.independent_text:
            expected = {'type': 'independent-codex',
                'request_sha256': hashlib.sha256((directory / 'request.json').read_bytes()).hexdigest(),
                'response_sha256': hashlib.sha256(result.encode('utf-8')).hexdigest()}
            if response.get('host') != expected:
                raise ValueError('Independent Codex text host evidence is required')
        return [result]

    async def _review_text(self, model_name, contents, settings, multiturn_input, retry_options, contract):
        """원본 검토 응답만 최대 2회 검사하고 유효 판단 이후 단계 연결."""
        record = {'stage': contract['stage'], 'final': contract.get('final', False), 'status': 'running', 'attempts': []}
        self.review_calls.append(record)
        retry_contents, retry_multiturn = contents, multiturn_input
        for number in (1, 2):
            directory, response = await self._exchange(model_name, retry_contents, settings,
                retry_multiturn, retry_options, review_attempt={
                    'stage': contract['stage'], 'number': number, 'final': contract.get('final', False)})
            if 'error' in response:
                raise RuntimeError(response['error'])
            result = response['text']
            if self.independent_text or contract.get('final', False):
                expected = {'type': 'independent-codex',
                    'request_sha256': hashlib.sha256((directory / 'request.json').read_bytes()).hexdigest(),
                    'response_sha256': hashlib.sha256(result.encode('utf-8')).hexdigest()}
                if response.get('host') != expected:
                    raise ValueError('Independent Codex text host evidence is required')
            attempt = {'request_id': directory.name, 'number': number}
            record['attempts'].append(attempt)
            try:
                if not isinstance(result, str) or not result.strip():
                    raise ValueError('A non-empty review response is required')
                valid = validate_review(result, contract)
            except ValueError as error:
                attempt.update(status='invalid_response', error=str(error))
                write_json(directory / 'outcome.json', attempt)
                write_json(self.directory / 'review_validation.json', self.review_calls)
                if number == 2:
                    record.update(status='review_failed', error=str(error))
                    write_json(self.directory / 'review_validation.json', self.review_calls)
                    raise ReviewResponseError(f'{contract["stage"]} failed response validation twice: {error}') from error
                from google.genai import types
                retry_contents = [*contents] if multiturn_input else [contents]
                retry_contents += [types.Content(role='model', parts=[types.Part.from_text(text=result)]),
                    [{'type': 'text', 'text': 'The previous response failed validation: ' + str(error)
                      + '. Answer the same original step again using its exact required format. Do not proceed to another step.'}]]
                retry_multiturn = True
                continue
            attempt['status'] = 'valid'
            contract['response'] = valid
            record.update(status='valid', response=valid)
            write_json(directory / 'outcome.json', attempt)
            write_json(self.directory / 'review_validation.json', self.review_calls)
            if contract.get('stop_after_gate'):
                raise ReviewDecision(valid)
            return [valid]

    async def _exchange(self, model_name, contents, settings, multiturn_input, retry_options,
                        image_attempt=None, review_attempt=None):
        """개별 시도의 불변 요청과 응답 연결 및 이미지 timeout 기록."""
        kind = 'image' if 'IMAGE' in settings.get('response_modalities', []) else 'text'
        request_id = uuid.uuid4().hex
        directory = self.directory / request_id
        directory.mkdir()
        turns = contents if multiturn_input else [contents]
        request = {'id': request_id, 'kind': kind, 'model_name': model_name,
                   'config': settings, 'retry_options': retry_options,
                   'turns': [self._turn(turn, directory) for turn in turns]}
        if kind == 'text' and self.canvas_ratio is not None:
            request['canvas_constraint'] = {'aspect_ratio': self.canvas_ratio}
            request['turns'][-1]['content'].append(
                {'type': 'text', 'text': canvas_instruction(self.canvas_ratio)})
        if kind == 'text' and (self.independent_text or (review_attempt and review_attempt['final'])):
            request['required_text_host'] = 'independent-codex'
        if review_attempt is not None:
            request['review_validation'] = review_attempt
        if image_attempt is not None:
            request['image_attempt'] = image_attempt
        write_json(directory / 'request.json', request)
        self.request_paths.append(directory / 'request.json')
        print(f'PAPER_SKETCH_REQUEST {directory / "request.json"}', flush=True)
        response_path = directory / 'response.json'
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.timeout
        while not response_path.exists():
            if loop.time() >= deadline:
                if kind == 'image':
                    response = {'id': request_id, 'error': 'Host response timed out; generation state unknown',
                                'error_type': 'timeout'}
                    write_json(directory / 'outcome.json', {'status': 'timed_out', **response})
                    return directory, response
                raise TimeoutError(f'Host response not received: {directory}')
            await asyncio.sleep(0.1)
        response = json.loads(response_path.read_text(encoding='utf-8'))
        if response['id'] != request_id:
            raise ValueError('Response ID does not match request')
        return directory, response

    async def _image(self, model_name, contents, settings, multiturn_input, retry_options):
        """확인된 일시 오류만 재시도하고 소진 시 원본 실패 반환 계약 유지."""
        from PIL import Image
        limit = retry_options.get('max_attempts', 5)
        delay = retry_options.get('retry_delay', 30)
        if not isinstance(limit, int) or limit < 1 or delay < 0:
            raise ValueError('Invalid image retry budget')
        call = {'id': uuid.uuid4().hex, 'status': 'running', 'attempts': []}
        self.image_calls.append(call)
        audit_path = self.directory / 'image_generation.json'
        if self.image_blocked is not None:
            call.update(status='failed', blocked_by=self.image_blocked)
            write_json(audit_path, self.image_calls)
            return ['Error']
        for number in range(1, limit + 1):
            write_json(audit_path, self.image_calls)
            directory, response = await self._exchange(model_name, contents, settings, multiturn_input,
                retry_options, {'call_id': call['id'], 'number': number, 'max_attempts': limit})
            attempt = {'request_id': directory.name, 'number': number}
            call['attempts'].append(attempt)
            if 'error' in response:
                category = response.get('error_type', 'unknown')
                if category not in ('transient', 'quota', 'refused', 'invalid_input', 'fatal', 'unknown', 'timeout'):
                    raise ValueError(f'Unknown image error type: {category}')
                attempt.update(error_type=category, error=response['error'])
                if category in ('quota', 'timeout'):
                    self.image_blocked = {'request_id': directory.name, 'error_type': category,
                                          'error': response['error']}
                if category in ('invalid_input', 'fatal'):
                    call['status'] = 'fatal'
                    write_json(directory / 'outcome.json', {'status': 'fatal', **attempt})
                    write_json(audit_path, self.image_calls)
                    raise RuntimeError(response['error'])
            else:
                path = Path(response['image_path'])
                if not path.is_absolute():
                    raise ValueError('image_path must be absolute')
                try:
                    raw = path.read_bytes()
                    with Image.open(io.BytesIO(raw)) as image:
                        width, height = image.size
                        image.verify()
                except OSError as error:
                    attempt.update(error_type='invalid_image', error=str(error))
                else:
                    ratio = assess_ratio(width, height, settings.get('image_config', {}).get('aspect_ratio'))
                    attempt['image_ratio'] = ratio
                    if ratio['warning']:
                        print('PAPER_SKETCH_RATIO_WARNING ' + json.dumps(
                            {'request_id': directory.name, **ratio}), flush=True)
                    attempt['status'] = 'succeeded'
                    call['status'] = 'succeeded'
                    write_json(directory / 'outcome.json', attempt)
                    write_json(audit_path, self.image_calls)
                    return [base64.b64encode(raw).decode('ascii')]
            retry = attempt['error_type'] == 'transient' and number < limit
            attempt['status'] = 'retrying' if retry else 'failed'
            call['status'] = 'running' if retry else 'failed'
            write_json(directory / 'outcome.json', attempt)
            write_json(audit_path, self.image_calls)
            if not retry:
                # 원본 Visualizer가 변환 실패로 표시하여 같은 설명의 재요청 방지
                return ['Error']
            await asyncio.sleep(delay)


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
