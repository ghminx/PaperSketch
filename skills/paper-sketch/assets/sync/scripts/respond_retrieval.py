
"""단일 그룹 검색 요청을 독립 Codex CLI 문맥에서 처리 후 bridge에 제출."""
import time
import threading
import argparse
from collections.abc import Sequence
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from bridge import write_json

def _permission_failure(phase: str) -> dict:
    """확인된 Codex 실행 권한 오류를 모델 판단 실패와 구분."""
    return {'error': 'Codex host permission denied while accessing its local runtime (state DB, temporary files or app-server). Request the required host execution permissions under the current approval policy; do not repeat this request under unchanged permissions. No automatic retry was performed.', 'error_type': 'host_permission_denied', 'failure_phase': phase, 'retryable': False}

def _permission_denied(text: str) -> bool:
    """실제 OS 권한 거부 표현만 식별하며 DB 오류 일반화 방지."""
    lines = [line.casefold() for line in text.splitlines() if not line.lstrip().casefold().startswith('warning:') and ' WARN ' not in line]
    return any((marker in line for line in lines for marker in ('access is denied', 'permission denied', 'os error 5', '액세스가 거부', 'winerror 5')))

def retrieval_prompt(request: dict) -> str:
    """단일 검색 요청의 지침과 전문을 CLI 입력으로 구성."""
    if request['kind'] != 'text' or len(request['turns']) != 1 or request['turns'][0]['role'] != 'user' or any((part['type'] != 'text' for part in request['turns'][0]['content'])) or ('selected_diagrams' not in request['config']['system_instruction']):
        raise ValueError('Expected a single grouped-retrieval text request')
    user = '\n'.join((part['text'] for part in request['turns'][0]['content']))
    prompt = 'Perform only the retrieval task. Do not use tools or read files. Return JSON only.\n\n' + 'SYSTEM INSTRUCTION:\n' + request['config']['system_instruction'] + '\n\nUSER INPUT:\n' + user
    if len(prompt) > 1048576:
        raise ValueError('Retrieval host prompt exceeds the observed CLI character limit')
    return prompt

def main():
    """기존 ChatGPT 인증만 사용하여 검색 응답과 실제 호출 기록 저장."""
    parser = argparse.ArgumentParser()
    parser.add_argument('request', type=Path)
    parser.add_argument('--model', required=True)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    submit_text(args.request, model=args.model, timeout=args.timeout, prompt_builder=lambda request: (retrieval_prompt(request), ()))

def submit_text(request_path: Path, *, model: str, timeout: float, prompt: str | None=None, images: Sequence[Path]=(), prompt_builder=None):
    """독립 실행의 입력·이미지·이벤트·응답 및 연결 근거 저장."""
    request_path = request_path.resolve()
    request = json.loads(request_path.read_text(encoding='utf-8'))
    directory = request_path.parent
    response_path = directory / 'response.json'
    if response_path.exists() or (directory / 'codex-host').exists():
        raise FileExistsError('Request has a response or prior Codex host attempt')
    try:
        if prompt_builder is not None:
            prompt, images = prompt_builder(request)
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError('A non-empty host prompt is required')
        _execute_text(request_path, request, model=model, timeout=timeout, prompt=prompt, images=images)
    except FileExistsError:
        raise
    except (OSError, RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        if not response_path.exists():
            failure = _permission_failure('host_preflight') if isinstance(error, PermissionError) else {'error': str(error), 'error_type': 'host_failure'}
            write_json(response_path, {'id': request['id'], **failure, 'exception': type(error).__name__})
        raise

def _execute_text(request_path: Path, request: dict, *, model: str, timeout: float, prompt: str, images: Sequence[Path]):
    """검증된 요청의 Codex 실행과 응답·근거 파일 저장."""
    directory = request_path.parent
    response_path = directory / 'response.json'
    exe = shutil.which('codex')
    if exe is None:
        raise RuntimeError('Codex CLI is required for independent text contexts')
    env = os.environ.copy()
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
        env.pop(key, None)
    login = subprocess.run([exe, 'login', 'status'], env=env, capture_output=True, timeout=15)
    if login.returncode and _permission_denied((login.stdout + login.stderr).decode('utf-8', errors='replace')):
        raise PermissionError('Codex login-status process could not access its local runtime')
    if login.returncode or b'ChatGPT' not in login.stdout + login.stderr:
        raise RuntimeError('This text host requires an existing ChatGPT Codex login')
    host = directory / 'codex-host'
    host.mkdir()
    (host / 'prompt.txt').write_text(prompt, encoding='utf-8')
    answer_path = host / 'answer.txt'
    command = [exe, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check', '-s', 'read-only', '-m', model, '-c', 'model_reasoning_effort="high"', '-c', 'project_doc_max_bytes=0', '-c', 'memories.use_memories=false', '-c', 'memories.generate_memories=false', '--json', '-o', str(answer_path)]
    for path in images:
        command.extend(['-i', str(path)])
    command.append('-')
    response = {'id': request['id']}
    with (host / 'events.jsonl').open('wb') as stdout, (host / 'stderr.log').open('wb') as stderr:
        try:
            result = subprocess.run(command, input=prompt.encode('utf-8'), env=env, stdout=stdout, stderr=stderr, timeout=timeout, cwd=host)
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = None
            response['error'] = 'Independent Codex text call timed out'
    events = []
    stderr_text = (host / 'stderr.log').read_text(encoding='utf-8', errors='replace')
    if exit_code is not None and exit_code != 0 and _permission_denied(stderr_text):
        response.update(_permission_failure('codex_exec'))
    for line in (host / 'events.jsonl').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            response.setdefault('error', 'Independent Codex text call produced an incomplete event log')
            break
    completed = [event for event in events if event['type'] == 'turn.completed']
    threads = [event['thread_id'] for event in events if event['type'] == 'thread.started']
    tools = [event for event in events if event.get('item', {}).get('type') not in (None, 'agent_message', 'reasoning')]
    if exit_code != 0 or len(completed) != 1 or len(threads) != 1 or tools or (not answer_path.exists()):
        response.setdefault('error', 'Independent Codex text call failed; inspect codex-host logs')
    elif not answer_path.read_text(encoding='utf-8').strip():
        if 'review_validation' in request:
            response['text'] = ''
        else:
            response['error'] = 'Independent Codex text call returned an empty response'
    else:
        response['text'] = answer_path.read_text(encoding='utf-8')
    if 'error' not in response:
        response['host'] = {'type': 'independent-codex', 'request_sha256': hashlib.sha256(request_path.read_bytes()).hexdigest(), 'response_sha256': hashlib.sha256(response['text'].encode('utf-8')).hexdigest()}
    write_json(host / 'metadata.json', {'request_sha256': hashlib.sha256(request_path.read_bytes()).hexdigest(), 'requested_model': model, 'reasoning_effort': 'high', 'auth': 'ChatGPT', 'independent_context': True, 'prompt_chars': len(prompt), 'thread_ids': threads, 'command': command, 'images': [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in images], 'exit_code': exit_code, 'usage': [event['usage'] for event in completed], 'failure': {key: response[key] for key in ('error_type', 'failure_phase', 'retryable') if key in response}})
    write_json(response_path, response)
    if 'error' in response:
        raise SystemExit(response['error'])
    print(json.dumps({'response': str(response_path), 'status': 'submitted'}))
if __name__ == '__main__':
    main()
