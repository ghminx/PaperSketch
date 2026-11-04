"""기본 샌드박스에서 소켓 없는 동기 CLI와 실제 데이터·렌더링 검증."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from standalone_smoke import CODE, prompts, write_json

BOOTSTRAP = '''import json,os,runpy,sys
def guard(event,args):
    if event in ('socket.__new__','socket.connect','socket.getaddrinfo'):
        raise PermissionError('Socket use forbidden in synchronous runtime test: '+event)
sys.addaudithook(guard)
sys.argv=sys.argv[1:]
sys.path.insert(0,os.path.dirname(sys.argv[0]))
runpy.run_path(sys.argv[0],run_name='__main__')
'''


def run_case(skill, work, task, *, prior=None, revise=False, image_failure=False):
    """실제 CLI 요청에 fixture 응답을 전달하고 결과·순서·원본 이력 확인."""
    from PIL import Image
    import re
    name = 'refine-failure' if image_failure else 'refine-yes' if revise else 'refine-no' if prior else task
    out = work / name
    source = work / (name + '-input.json')
    write_json(source, {'content': {'A': 10, 'B': 15, 'C': 12} if task == 'plot' else 'Synthetic input -> encoder -> output.',
                        'visual_intent': 'Synthetic connection test.', 'additional_info': {'rounded_ratio': '21:9'}})
    args = ['refine' if prior else 'generate', '--dataset-dir', str(skill / 'data' / task),
            '--output', str(out), '--timeout', '20']
    if prior:
        feedback = work / (name + '.txt')
        feedback.write_text('Make the box blue.' if revise else 'Keep the current figure.', encoding='utf-8')
        args += ['--prior', str(prior), '--feedback-file', str(feedback)]
    else:
        args += ['--task', task, '--input', str(source), '--retrieval', 'auto', '--critic-rounds', '1']
        if task == 'diagram':
            args += ['--reference-groups', str(skill / 'data/diagram/retrieval')]
    python = skill / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    pool = json.loads((skill / 'data' / task / 'ref.json').read_text(encoding='utf-8'))
    expected = prompts(skill, task)
    stages, selected = [], []
    group_count = 0
    gate_count = 0
    env = os.environ.copy()
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    with (work / (name + '-stdout.log')).open('wb') as stdout, (work / (name + '-stderr.log')).open('wb') as stderr:
        process = subprocess.Popen([str(python), '-B', '-u', '-c', BOOTSTRAP,
            str(skill / 'scripts/run.py'), *args], cwd=work, env=env, stdout=stdout, stderr=stderr)
        started = time.monotonic()
        try:
            while process.poll() is None:
                if time.monotonic() - started > 90:
                    raise TimeoutError('Synchronous fixture exceeded its test budget')
                for path in sorted(out.glob('requests/*/request.json')):
                    if path.with_name('response.json').exists():
                        continue
                    request = json.loads(path.read_text(encoding='utf-8'))
                    if request['kind'] == 'image':
                        stages.append('image')
                        if image_failure:
                            reply = {'error': 'Fixture quota exhausted', 'error_type': 'quota'}
                        else:
                            image = path.parent / 'fixture.png'
                            Image.new('RGB', (210, 90), 'blue' if revise else 'white').save(image)
                            reply = {'image_path': str(image)}
                    else:
                        system = request['config']['system_instruction']
                        contract = request.get('review_validation')
                        if contract:
                            stage = contract['stage']
                            fields = {'context': ['context_diagram1', 'context_user_turn1'],
                                'critique': ['critique_latest_turn', 'critique_source_content', 'critique_presentation'],
                                'rewrite': ['critic_suggestions', 'revised_description']}
                            if stage == 'gate':
                                gate_count += 1
                                text = 'YES' if revise and gate_count == 1 and not contract['final'] else 'NO'
                            else:
                                value = 'Blue box with the same encoder connection.' if prior and stage == 'rewrite' else 'No changes needed.' if stage == 'rewrite' else 'Fixture context/review.'
                                text = json.dumps({field: value for field in fields[stage]})
                        elif task == 'diagram' and 'selected_diagrams' in system:
                            stage = 'retrieval'
                            ids = re.findall(r'- Diagram ID: ([^\n]+)', request['turns'][0]['content'][0]['text'])
                            selected = ids[:6 if group_count < 4 else 10]
                            group_count += 1
                            text = json.dumps({'selected_diagrams': selected})
                        elif system == expected['retriever']:
                            stage = 'retrieval'
                            selected = [row['id'] for row in pool[:10]]
                            text = json.dumps({'top10_plots': selected})
                        elif system == expected['planner']:
                            stage = 'planner'
                            images = [p for t in request['turns'] for p in t['content'] if p['type'] == 'image']
                            assert len(images) == 10
                            by_id = {row['id']: row for row in pool}
                            for identifier, image in zip(selected, images):
                                assert Path(image['path']).read_bytes() == (skill / 'data' / task / by_id[identifier]['path_to_gt_image']).read_bytes()
                            text = 'Fixture initial description.'
                        elif system == expected['stylist']:
                            stage, text = 'stylist', 'Fixture styled description.'
                        elif system == expected['visualizer'] and task == 'plot':
                            stage, text = 'plot_code', CODE
                        else:
                            raise AssertionError('Unexpected model request')
                        stages.append(stage)
                        reply = {'text': text, 'host': {'type': 'independent-codex',
                            'request_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                            'response_sha256': hashlib.sha256(text.encode()).hexdigest()}}
                    write_json(path.with_name('response.json'), {'id': request['id'], **reply})
                time.sleep(.02)
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
    assert process.returncode == 0, (work / (name + '-stderr.log')).read_text(encoding='utf-8')
    record = json.loads((out / 'result.json').read_text(encoding='utf-8'))
    assert record['final_review']['status'] == ('issues_remaining' if image_failure else 'passed')
    assert (out / 'final.jpg').is_file()
    if prior and (not revise or image_failure):
        assert (out / 'final.jpg').read_bytes() == prior.with_name('final.jpg').read_bytes()
    if image_failure:
        assert record['image_generation_status'] == 'completed_with_image_failures'
    if task == 'plot':
        assert (out / 'final.py').read_text(encoding='utf-8').strip() == CODE.strip()
    # inspect와 선택도 동기 CLI로 재개 가능함을 확인
    for action in [['inspect', '--prior', str(out / 'result.json')],
                   ['select', '--prior', str(out / 'result.json'), '--image-field', record['eval_image_field'], '--output', str(work / (name + '-selected'))]]:
        checked = subprocess.run([str(python), '-B', '-c', BOOTSTRAP, str(skill / 'scripts/run.py'), *action],
            cwd=work, env=env, capture_output=True, timeout=15)
        assert checked.returncode == 0, checked.stderr.decode('utf-8')
        json.loads(checked.stdout)
    return {'case': name, 'stages': stages, 'seconds': round(time.monotonic() - started, 2), 'status': 'passed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--skill', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    skill, work = args.skill.resolve(), args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    cases = [run_case(skill, work, 'diagram')]
    prior = work / 'diagram/result.json'
    cases += [run_case(skill, work, 'diagram', prior=prior), run_case(skill, work, 'diagram', prior=prior, revise=True),
              run_case(skill, work, 'diagram', prior=prior, revise=True, image_failure=True), run_case(skill, work, 'plot')]
    report = {'socket_creation': 'forbidden in runtime children', 'live_models': False, 'cases': cases}
    write_json(work / 'report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
