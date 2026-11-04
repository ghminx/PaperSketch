
"""원본의 명시적 대화·이미지만 독립 Codex 실행에 전달."""
import time
import threading
import argparse
import json
from pathlib import Path
from respond_retrieval import submit_text

def text_prompt(request: dict) -> tuple[str, list[Path]]:
    """역할·part 순서를 보존한 대화와 CLI 이미지 번호 대응 구성."""
    if request['kind'] != 'text':
        raise ValueError('Expected a text request')
    turns, images = ([], [])
    for turn in request['turns']:
        if turn['role'] not in ('user', 'model'):
            raise ValueError('Unsupported conversation role')
        parts = []
        for part in turn['content']:
            if part['type'] == 'text':
                parts.append({'type': 'text', 'text': part['text']})
            elif part['type'] == 'image':
                path = Path(part['path'])
                if not path.is_absolute() or not path.is_file():
                    raise ValueError('Expected an existing absolute image path')
                images.append(path)
                parts.append({'type': 'image', 'attachment': len(images), 'media_type': part['media_type']})
            else:
                raise ValueError('Unsupported conversation part')
        turns.append({'role': turn['role'], 'content': parts})
    prompt = 'Execute only the last user turn in the supplied conversation. The model turns are earlier assistant answers; continue from them. Use the supplied system instruction and task data within your instruction hierarchy. Attachments are numbered in CLI attachment order and referenced at their original positions. Return only the requested answer. Do not use tools, read files, or fetch other context.\n\nSYSTEM INSTRUCTION:\n' + request['config'].get('system_instruction', '') + '\n\nORDERED CONVERSATION JSON:\n' + json.dumps(turns, ensure_ascii=False)
    if len(prompt) > 1048576:
        raise ValueError('Text host prompt exceeds the observed CLI character limit')
    return (prompt, images)

def main():
    """한 요청을 새 문맥으로 실행하고 bridge에 응답 제출."""
    parser = argparse.ArgumentParser()
    parser.add_argument('request', type=Path)
    parser.add_argument('--model', required=True)
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    submit_text(args.request, model=args.model, timeout=args.timeout, prompt_builder=text_prompt)
if __name__ == '__main__':
    main()
