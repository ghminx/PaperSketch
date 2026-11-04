
import time
import threading
import argparse
import json
from pathlib import Path
from bridge import write_json

def image_prompt(request: dict) -> str:
    """원문 렌더링 지시와 API 비율 설정을 내장 도구 입력으로 결합."""
    if request['kind'] != 'image':
        raise ValueError('Expected an image request')
    if len(request['turns']) != 1 or any((p['type'] != 'text' for p in request['turns'][0]['content'])):
        raise ValueError('Only the original text-to-image Visualizer request is supported')
    original = '\n'.join((part['text'] for part in request['turns'][0]['content']))
    ratio = request['config']['image_config']['aspect_ratio']
    return f'Image API setting: aspect_ratio = {ratio}. Use this canvas ratio.\n\n{original}'

def main():
    """host 응답 제출 또는 비율 설정을 반영한 이미지 지시 준비."""
    parser = argparse.ArgumentParser()
    parser.add_argument('request', type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--text-file', type=Path)
    group.add_argument('--image-file', type=Path)
    group.add_argument('--error')
    group.add_argument('--prepare-image-prompt', type=Path)
    parser.add_argument('--error-type', choices=['transient', 'quota', 'refused', 'invalid_input', 'fatal', 'unknown'], default='unknown')
    args = parser.parse_args()
    request = json.loads(args.request.read_text(encoding='utf-8'))
    outcome_path = args.request.parent / 'outcome.json'
    if outcome_path.exists():
        raise ValueError('This request attempt is already closed; use the latest pending request')
    if args.error_type != 'unknown' and (args.error is None or request['kind'] != 'image'):
        raise ValueError('error-type applies only to image errors')
    if args.prepare_image_prompt:
        prompt = image_prompt(request)
        with args.prepare_image_prompt.open('x', encoding='utf-8') as output:
            output.write(prompt)
        return
    path = args.request.parent / 'response.json'
    if path.exists():
        raise FileExistsError(path)
    response = {'id': request['id']}
    if args.error is not None:
        response['error'] = args.error
        if request['kind'] == 'image':
            response['error_type'] = args.error_type
    elif args.text_file:
        if request.get('required_text_host') == 'independent-codex':
            raise ValueError('Use respond_text.py for independent Codex text requests')
        if request['kind'] != 'text':
            raise ValueError('Text response supplied for an image request')
        response['text'] = args.text_file.read_text(encoding='utf-8')
    else:
        if request['kind'] != 'image':
            raise ValueError('Image response supplied for a text request')
        response['image_path'] = str(args.image_file.resolve(strict=True))
    write_json(path, response)
if __name__ == '__main__':
    main()
