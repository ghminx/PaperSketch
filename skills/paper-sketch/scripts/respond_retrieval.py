"""단일 그룹 검색 요청을 독립 Codex CLI 문맥에서 처리 후 bridge에 제출."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from bridge import write_json


def retrieval_prompt(request: dict) -> str:
    """단일 검색 요청의 지침과 전문을 CLI 입력으로 구성."""
    if (request['kind'] != 'text' or len(request['turns']) != 1
            or request['turns'][0]['role'] != 'user'
            or any(part['type'] != 'text' for part in request['turns'][0]['content'])
            or 'selected_diagrams' not in request['config']['system_instruction']):
        raise ValueError('Expected a single grouped-retrieval text request')
    user = '\n'.join(part['text'] for part in request['turns'][0]['content'])
    prompt = ('Perform only the retrieval task. Do not use tools or read files. Return JSON only.\n\n'
              + 'SYSTEM INSTRUCTION:\n' + request['config']['system_instruction']
              + '\n\nUSER INPUT:\n' + user)
    if len(prompt) > 1_048_576:
        raise ValueError('Retrieval host prompt exceeds the observed CLI character limit')
    return prompt


def main():
    """기존 ChatGPT 인증만 사용하여 검색 응답과 실제 호출 기록 저장."""
    parser = argparse.ArgumentParser()
    parser.add_argument('request', type=Path)
    parser.add_argument('--model', required=True)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    directory = args.request.resolve().parent
    response_path = directory / 'response.json'
    if response_path.exists() or (directory / 'codex-host').exists():
        raise FileExistsError('Request has a response or prior Codex host attempt')
    prompt = retrieval_prompt(request)
    exe = shutil.which('codex')
    if exe is None:
        raise RuntimeError('Codex CLI is required for independent retrieval contexts')
    env = os.environ.copy()
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
        env.pop(key, None)
    login = subprocess.run([exe, 'login', 'status'], env=env, capture_output=True, timeout=15)
    if login.returncode or b'ChatGPT' not in login.stdout + login.stderr:
        raise RuntimeError('This retrieval host requires an existing ChatGPT Codex login')
    host = directory / 'codex-host'
    host.mkdir()
    (host / 'prompt.txt').write_text(prompt, encoding='utf-8')
    answer_path = host / 'answer.txt'
    command = [exe, 'exec', '--ignore-user-config', '--ephemeral', '--skip-git-repo-check',
               '-s', 'read-only', '-m', args.model, '-c', 'model_reasoning_effort="high"',
               '--json', '-o', str(answer_path), '-']
    response = {'id': request['id']}
    with (host / 'events.jsonl').open('wb') as stdout, (host / 'stderr.log').open('wb') as stderr:
        try:
            result = subprocess.run(command, input=prompt.encode('utf-8'), env=env,
                                    stdout=stdout, stderr=stderr, timeout=args.timeout)
            exit_code = result.returncode
        except subprocess.TimeoutExpired:
            exit_code = None
            response['error'] = 'Independent Codex retrieval call timed out'
    events = []
    for line in (host / 'events.jsonl').read_text(encoding='utf-8').splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            response['error'] = 'Independent Codex retrieval produced an incomplete event log'
            break
    completed = [event for event in events if event['type'] == 'turn.completed']
    tools = [event for event in events if event.get('item', {}).get('type') not in (None, 'agent_message', 'reasoning')]
    if exit_code != 0 or not completed or tools or not answer_path.exists():
        response.setdefault('error', 'Independent Codex retrieval failed; inspect codex-host logs')
    elif not answer_path.read_text(encoding='utf-8').strip():
        response['error'] = 'Independent Codex retrieval returned an empty response'
    else:
        response['text'] = answer_path.read_text(encoding='utf-8')
    write_json(host / 'metadata.json', {'requested_model': args.model, 'reasoning_effort': 'high',
               'auth': 'ChatGPT', 'independent_context': True, 'prompt_chars': len(prompt),
               'exit_code': exit_code, 'usage': [event['usage'] for event in completed]})
    write_json(response_path, response)
    if 'error' in response:
        raise SystemExit(response['error'])
    print(json.dumps({'response': str(response_path), 'status': 'submitted'}))


if __name__ == '__main__':
    main()
