
"""요청 옵션과 관측된 검색·호출·선택 이력을 구분한 실행 기록."""
import time
import threading
import base64
import copy
import hashlib
import json
from pathlib import Path

def image_identity(data: dict) -> dict:
    """현재 선택 그림의 field와 decoded bytes hash 반환."""
    field = data['eval_image_field']
    return {'image_field': field, 'image_sha256': hashlib.sha256(base64.b64decode(data[field], validate=True)).hexdigest()}

def begin_execution(args, data: dict, *, parent: Path | None=None) -> dict:
    """현재 실행의 요청·부모 선택을 캡처하고 이전 실행 기록 보존."""
    previous = data.get('execution_record')
    if previous is not None:
        data['execution_history'] = [*data.get('execution_history', []), copy.deepcopy(previous)]
    ids = data.get('top10_references')
    origin = {'mode': 'unverified', 'selected_ids': ids, 'reason': 'No recorded retrieval origin; legacy CLI defaults are not evidence of execution'}
    if previous is not None:
        inherited = previous['retrieval']['origin']
        if inherited['selected_ids'] == ids:
            origin = copy.deepcopy(inherited)
    requested = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    record = {'format_version': 1, 'action': args.action, 'status': 'running', 'requested_options': requested, 'parent': None, 'retrieval': {'this_run': 'not_run', 'status': 'not_run', 'origin': origin}, 'calls': [], 'selected_output': None}
    if parent is not None:
        record['parent'] = {'path': str(parent.resolve()), 'result_sha256': hashlib.sha256(parent.read_bytes()).hexdigest(), 'selected_input': image_identity(data)}
    data['execution_record'] = record
    return record

def retrieval_started(data: dict):
    """실제로 검색 준비에 진입한 사실만 기록."""
    if 'execution_record' in data:
        data['execution_record']['retrieval'].update(this_run='attempted', status='incomplete')

def retrieval_completed(data: dict, mode: str, dataset: Path):
    """검색 완료·검증 이후 실제 선택 방식과 ID·데이터 식별 정보 기록."""
    if 'execution_record' not in data:
        return
    origin = {'mode': mode, 'selected_ids': list(data['top10_references']), 'generation_output': data['execution_record']['requested_options']['output']}
    if mode != 'none':
        origin['source_ref_sha256'] = hashlib.sha256((dataset / 'ref.json').read_bytes()).hexdigest()
    if mode == 'auto':
        audit = data['retrieval_audit']
        origin.update(strategy=audit['strategy'], groups_manifest_sha256=audit['groups_manifest_sha256'])
    data['execution_record']['retrieval'] = {'this_run': 'disabled' if mode == 'none' else 'performed', 'status': 'complete', 'origin': origin}

def observed_calls(paths: list[Path]) -> list[dict]:
    """이번 실행의 요청 파일과 hash로 연결된 host 메타데이터만 요약."""
    calls = []
    for path in paths:
        request_raw = path.read_bytes()
        request = json.loads(request_raw)
        request_hash = hashlib.sha256(request_raw).hexdigest()
        response_path = path.with_name('response.json')
        response = None
        response_status = 'missing'
        if response_path.exists():
            try:
                response = json.loads(response_path.read_text(encoding='utf-8'))
                response_status = 'invalid_structure' if not isinstance(response, dict) else 'error' if 'error' in response else 'received'
            except json.JSONDecodeError:
                response_status = 'invalid_json'
        call = {'request_id': request['id'], 'kind': request['kind'], 'request_file': path.relative_to(path.parent.parent.parent).as_posix(), 'request_sha256': request_hash, 'connector_name': request['model_name'], 'response_status': response_status, 'host': 'unverified', 'requested_model': 'unverified', 'requested_reasoning_effort': 'unverified', 'backend_model_version': 'unverified', 'applied_sampling': 'unverified', 'actual_tool': 'unverified'}
        if response_path.exists():
            call['response_file_sha256'] = hashlib.sha256(response_path.read_bytes()).hexdigest()
        metadata_path = path.parent / 'codex-host/metadata.json'
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                call['host_metadata_error'] = 'invalid_json'
                calls.append(call)
                continue
            if not isinstance(metadata, dict):
                call['host_metadata_error'] = 'invalid_structure'
            elif metadata.get('request_sha256') == request_hash and all((k in metadata for k in ('requested_model', 'reasoning_effort', 'exit_code', 'thread_ids'))):
                call.update(host='independent-codex', actual_tool='codex_exec', requested_model=metadata['requested_model'], requested_reasoning_effort=metadata['reasoning_effort'], host_metadata_sha256=hashlib.sha256(metadata_path.read_bytes()).hexdigest(), host_exit_code=metadata['exit_code'], thread_ids=metadata['thread_ids'])
        calls.append(call)
    return calls

def finish_execution(data: dict, paths: list[Path], status: str):
    """기존 처리 결과를 바꾸지 않고 이번 요청·최종 선택·종료 상태 기록."""
    record = data['execution_record']
    record['status'] = status
    record['calls'] = observed_calls(paths)
    record['bridge_request_counts'] = {kind: sum((c['kind'] == kind for c in record['calls'])) for kind in ('text', 'image')}
    record['feedback_turn_count'] = sum((t['role'] == 'user' for t in data.get('chat_history', [])))
    if data.get('eval_image_field') and data.get(data['eval_image_field']):
        record['selected_output'] = image_identity(data)
