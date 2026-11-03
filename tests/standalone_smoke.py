"""독립 설치에서 모의 모델·실제 데이터·Matplotlib로 전체 연결 검증."""
import argparse
import asyncio
import ast
import hashlib
import json
import os
from pathlib import Path
import sys


BOOTSTRAP = r'''
import json, os, runpy, sys
forbidden = [os.path.normcase(os.path.abspath(p)) for p in json.loads(sys.argv[1])]
def guard(event, args):
    if event == 'open' and isinstance(args[0], (str, bytes, os.PathLike)):
        path = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
        if any(path == root or path.startswith(root + os.sep) for root in forbidden):
            raise PermissionError('Development/source checkout access blocked: ' + path)
sys.addaudithook(guard)
sys.argv = sys.argv[2:]
sys.path.insert(0, os.path.dirname(sys.argv[0]))
runpy.run_path(sys.argv[0], run_name='__main__')
'''

CODE = """import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(5, 3))
ax.bar(['A', 'B', 'C'], [10, 15, 12])
ax.set_ylabel('Value')
fig.tight_layout()
"""


def write_json(path, value):
    """응답 부분 파일 노출을 피하는 원자적 fixture 저장."""
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    temporary.replace(path)


def prompts(skill, task):
    """설치된 원본 에이전트의 prompt 상수 조회."""
    vendor = 'interact' if task == 'diagram' else 'paperbanana_plot'
    result = {}
    for agent in ('retriever', 'planner', 'stylist', 'visualizer', 'critic'):
        if task == 'diagram' and agent == 'visualizer':
            continue
        tree = ast.parse((skill / f'assets/{vendor}/agents/{agent}_agent.py').read_text(encoding='utf-8'))
        key = f'{task.upper()}_{agent.upper()}_AGENT_SYSTEM_PROMPT'
        result[agent] = next(ast.literal_eval(node.value) for node in tree.body
                             if isinstance(node, ast.Assign) and any(
                                 isinstance(target, ast.Name) and target.id == key for target in node.targets))
    return result


async def run_case(skill, work, task, forbidden, *, prior=None):
    """설치된 Python 실행 후 모든 bridge 요청에 명시적 모의 응답 제출."""
    from PIL import Image
    import re

    python = skill / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    output = work / ('refined' if prior else task)
    arguments = ['refine' if prior else 'generate', '--dataset-dir', str(skill / 'data' / task),
                 '--output', str(output), '--timeout', '20']
    if prior:
        feedback = work / 'feedback.txt'
        feedback.write_text('Keep the current fixture figure.', encoding='utf-8')
        arguments += ['--prior', str(prior), '--feedback-file', str(feedback)]
    else:
        input_path = work / f'{task}-input.json'
        write_json(input_path, {'content': {'A': 10, 'B': 15, 'C': 12} if task == 'plot' else 'Input -> Encoder -> Output.',
                               'visual_intent': 'Simple fixture figure.', 'additional_info': {'rounded_ratio': '21:9'}})
        arguments += ['--task', task, '--input', str(input_path), '--retrieval', 'auto', '--critic-rounds', '1']
        if task == 'diagram':
            arguments += ['--reference-groups', str(skill / 'data/diagram/retrieval')]
    environment = os.environ.copy()
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    environment.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
    expected = prompts(skill, task)
    pool = json.loads((skill / 'data' / task / 'ref.json').read_text(encoding='utf-8'))
    selected = []
    stages, requests = [], []
    errors_path = work / f'{output.name}-stderr.log'
    with errors_path.open('wb') as errors:
        process = await asyncio.create_subprocess_exec(str(python), '-B', '-c', BOOTSTRAP,
            json.dumps(forbidden), str(skill / 'scripts/run.py'), *arguments, cwd=work, env=environment,
            stdout=asyncio.subprocess.PIPE, stderr=errors)
        try:
            while raw := await asyncio.wait_for(process.stdout.readline(), 90):
                line = raw.decode('utf-8').strip()
                if not line.startswith('PAPER_SKETCH_REQUEST '):
                    continue
                path = Path(line.removeprefix('PAPER_SKETCH_REQUEST '))
                assert path.is_relative_to(output)
                request = json.loads(path.read_text(encoding='utf-8'))
                requests.append(str(path))
                if request['kind'] == 'image':
                    image = path.parent / 'fixture.png'
                    Image.new('RGB', (210, 90), 'white').save(image)
                    write_json(path.with_name('response.json'), {'id': request['id'], 'image_path': str(image)})
                    stages.append('image_fixture')
                    continue
                prompt = request['config']['system_instruction']
                contract = request.get('review_validation')
                if contract:
                    stage = contract['stage']
                    fields = {'rewrite': ['critic_suggestions', 'revised_description'],
                              'context': ['context_diagram1', 'context_user_turn1'],
                              'critique': ['critique_latest_turn', 'critique_source_content', 'critique_presentation']}
                    text = 'NO' if stage == 'gate' else json.dumps({
                        key: 'No changes needed.' if stage == 'rewrite' else 'Fixture review/context.'
                        for key in fields[stage]})
                elif task == 'diagram' and 'selected_diagrams' in prompt:
                    stage = 'grouped_retrieval'
                    body = request['turns'][0]['content'][0]['text']
                    ids = re.findall(r'- Diagram ID: ([^\n]+)', body)
                    count = 10 if len(stages) == 4 else 6
                    selected = ids[:count]
                    text = json.dumps({'selected_diagrams': selected})
                elif prompt == expected['retriever']:
                    stage = 'retriever'
                    selected = [row['id'] for row in pool[:10]]
                    text = json.dumps({'top10_plots': selected})
                elif prompt == expected['planner']:
                    stage = 'planner'
                    images = [p for turn in request['turns'] for p in turn['content'] if p['type'] == 'image']
                    assert len(images) == 10
                    by_id = {row['id']: row for row in pool}
                    for identifier, image in zip(selected, images):
                        assert Path(image['path']).read_bytes() == (skill / 'data' / task / by_id[identifier]['path_to_gt_image']).read_bytes()
                    text = 'Fixture initial description.'
                elif prompt == expected['stylist']:
                    stage, text = 'stylist', 'Fixture styled description.'
                elif prompt == expected['visualizer'] and task == 'plot':
                    stage, text = 'plot_code_fixture', CODE
                else:
                    raise AssertionError('Unexpected request: ' + prompt[:100])
                stages.append(stage)
                write_json(path.with_name('response.json'), {'id': request['id'], 'text': text,
                    'host': {'type': 'independent-codex',
                        'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'response_sha256': hashlib.sha256(text.encode()).hexdigest()}})
            await asyncio.wait_for(process.wait(), 30)
            if process.returncode:
                raise AssertionError(errors_path.read_text(encoding='utf-8'))
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
    assert (output / 'final.jpg').is_file()
    record = json.loads((output / 'result.json').read_text(encoding='utf-8'))
    assert record['final_review']['status'] == 'passed'
    if task == 'plot':
        assert (output / 'final.py').read_text(encoding='utf-8').strip() == CODE.strip()
    if prior:
        assert 'image_fixture' not in stages
        assert (output / 'final.jpg').read_bytes() == prior.with_name('final.jpg').read_bytes()
    return {'task': 'refine_no_change' if prior else task, 'requests': len(requests), 'stages': stages,
            'result': str(output / 'result.json'), 'review': record['final_review']['status']}


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    parser.add_argument('--forbid', action='append', default=[])
    args = parser.parse_args()
    skill, work = args.skill.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    reports = [await run_case(skill, work, 'diagram', args.forbid)]
    reports.append(await run_case(skill, work, 'diagram', args.forbid, prior=work / 'diagram/result.json'))
    reports.append(await run_case(skill, work, 'plot', args.forbid))
    report = {'scope': 'mock text/image responses; real datasets, pipelines, Matplotlib and persistence',
              'live_model_calls': 0, 'forbidden_checkouts': args.forbid, 'cases': reports}
    write_json(work / 'report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
