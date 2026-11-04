
"""PaperBanana Plot 원본 agent의 데이터·검토·실행 연결."""
import time
import threading
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid
from PIL import Image
from bridge import write_json
from review_protocol import review_plan
from review_agents import REWRITE_FIELDS, review_record
from plot_code import prepare_plot_code
ASSETS = Path(__file__).resolve().parents[1] / 'assets'
sys.path.insert(0, str(ASSETS))
from paperbanana_plot.agents.retriever_agent import RetrieverAgent
from paperbanana_plot.agents.planner_agent import PlannerAgent
from paperbanana_plot.agents.stylist_agent import StylistAgent
from paperbanana_plot.agents.critic_agent import CriticAgent
from paperbanana_plot.agents.visualizer_agent import VisualizerAgent
from paperbanana_plot.utils.paperviz_processor import PaperVizProcessor

def reference_pool(dataset: Path) -> list[dict]:
    """Plot 참고 항목·중복 ID·실제 이미지 연결 확인."""
    pool = json.loads((dataset / 'ref.json').read_text(encoding='utf-8'))
    if len(pool) < 10 or len({row['id'] for row in pool}) != len(pool):
        raise ValueError('Plot references require at least ten distinct IDs')
    for row in pool:
        (row['content'], row['visual_intent'])
        image = (dataset / row['path_to_gt_image']).resolve()
        if not image.is_relative_to(dataset.resolve()):
            raise ValueError('Plot reference image leaves the dataset')
        with Image.open(image) as opened:
            opened.verify()
    return pool

class PlotRetriever(RetrieverAgent):
    """원본 전체 후보 검색 이후 반환 ID와 실제 pool 대응 확인."""

    def process(self, data, retrieval_setting='auto'):
        pool = reference_pool(self.exp_config.dataset_dir) if retrieval_setting != 'none' else []
        result = super().process(data, retrieval_setting)
        ids = result['top10_references']
        if retrieval_setting != 'none' and (not isinstance(ids, list) or len(ids) != 10 or any((not isinstance(i, str) for i in ids)) or (len(set(ids)) != 10) or (not set(ids).issubset({row['id'] for row in pool}))):
            raise ValueError('Expected ten distinct plot IDs from the full reference pool')
        origin = {'mode': retrieval_setting, 'selected_ids': ids, 'candidate_count': len(pool), 'strategy': 'upstream-full-pool-to10'}
        if pool:
            origin['source_ref_sha256'] = hashlib.sha256((self.exp_config.dataset_dir / 'ref.json').read_bytes()).hexdigest()
        result['retrieval_audit'] = origin
        result['execution_record']['retrieval'] = {'this_run': 'disabled' if retrieval_setting == 'none' else 'performed', 'status': 'complete', 'origin': origin}
        write_json(self.exp_config.output / 'retrieval.json', origin)
        return result

class PlotVisualizer(VisualizerAgent):
    """원본 설명·코드 생성 순서를 유지한 제한 시간 실행 연결."""

    def __init__(self, *, bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge
        self.calls = []

    def process(self, data):
        """원본 코드 응답을 보존하고 실제 실행 코드를 대응 필드에 연결."""
        start = len(self.calls)
        result = super().process(data)
        for call in self.calls[start:]:
            executed = (self.exp_config.output / call['job'] / 'code.py').read_bytes().decode('utf-8')
            for key, value in list(result.items()):
                if key.endswith('_code') and (not key.endswith('_executed_code')) and isinstance(value, str):
                    if hashlib.sha256(value.encode()).hexdigest() == call['code_sha256']:
                        result[key.removesuffix('_code') + '_executed_code'] = executed
        return result

    def execute_plot_code(self, raw_code, dpi):
        """원본 렌더러를 별도 프로세스에서 실행하고 성공·실패 보존."""
        directory = self.exp_config.output / 'plot-execution' / uuid.uuid4().hex
        directory.mkdir(parents=True)
        (directory / 'response.txt').write_text(raw_code, encoding='utf-8', newline='')
        code, repairs = prepare_plot_code(raw_code)
        (directory / 'code.py').write_text(code, encoding='utf-8', newline='')
        record = {'job': directory.relative_to(self.exp_config.output).as_posix(), 'text_request_id': self.bridge.request_paths[-1].parent.name, 'code_sha256': hashlib.sha256(raw_code.encode()).hexdigest(), 'executed_code_sha256': hashlib.sha256(code.encode()).hexdigest(), 'repairs': repairs, 'dpi': dpi, 'timeout_seconds': self.exp_config.plot_timeout, 'status': 'running'}
        self.calls.append(record)
        write_json(directory / 'request.json', record)
        write_json(self.exp_config.output / 'plot_execution.json', self.calls)
        env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR', 'PATH', 'TEMP', 'TMP') if key in os.environ}
        env.update(MPLCONFIGDIR=str(directory / 'mplconfig'), PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
        command = [sys.executable, '-I', '-B', str(Path(__file__).with_name('plot_worker.py')), '--job', str(directory)]
        started = time.monotonic()
        with (directory / 'stdout.log').open('wb') as stdout, (directory / 'stderr.log').open('wb') as stderr:
            try:
                completed = subprocess.run(command, cwd=directory, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, timeout=self.exp_config.plot_timeout)
                record['exit_code'] = completed.returncode
                record['status'] = 'invalid_code' if completed.returncode == 0 else 'worker_failed'
            except subprocess.TimeoutExpired:
                record.update(status='timeout', exit_code=None)
            except OSError as error:
                record.update(status='worker_failed', error=str(error))
        record['elapsed_seconds'] = round(time.monotonic() - started, 3)
        encoded = None
        image_path = directory / 'figure.jpg'
        if record['status'] == 'invalid_code' and image_path.is_file():
            try:
                with Image.open(image_path) as image:
                    record['width'], record['height'] = image.size
                    image.verify()
                raw = image_path.read_bytes()
                encoded = base64.b64encode(raw).decode('ascii')
                record.update(status='succeeded', image_sha256=hashlib.sha256(raw).hexdigest())
            except OSError as error:
                record.update(status='invalid_image', error=str(error))
        if (directory / 'worker.json').is_file():
            record['renderer'] = json.loads((directory / 'worker.json').read_text(encoding='utf-8'))
        write_json(directory / 'outcome.json', record)
        write_json(self.exp_config.output / 'plot_execution.json', self.calls)
        return encoded

class PlotCritic(CriticAgent):
    """원본 Plot 검토 입력을 유지한 응답 schema·그림 식별 검증."""

    def process(self, data, source='stylist'):
        index = data.get('current_critic_round', 0)
        field = 'target_plot_stylist_desc0_base64_jpg' if index == 0 else f'target_plot_critic_desc{index - 1}_base64_jpg'
        step = {'stage': 'rewrite', 'fields': REWRITE_FIELDS}
        with review_plan([step]):
            result = super().process(data, source)
        value = json.loads(step['response'])
        status = 'passed' if value['critic_suggestions'] == 'No changes needed.' else 'issues_remaining'
        record = review_record(data, field, status, value)
        result['_latest_review'] = record
        result.setdefault('review_history', []).append(record)
        return result

def make_plot_processor(args, bridge):
    """Plot 전용 원본 demo_full processor 구성."""
    cfg = SimpleNamespace(task_name='plot', dataset_dir=args.dataset_dir.resolve(), work_dir=ASSETS / 'paperbanana_plot', output=args.output.resolve(), main_model_name='codex-host', image_gen_model_name='matplotlib-local', temperature=1.0, exp_mode='demo_full', retrieval_setting=args.retrieval, max_critic_rounds=args.critic_rounds, plot_timeout=args.plot_timeout, planner_metaphor=False)
    return PaperVizProcessor(exp_config=cfg, vanilla_agent=None, polish_agent=None, retriever_agent=PlotRetriever(exp_config=cfg), planner_agent=PlannerAgent(exp_config=cfg), stylist_agent=StylistAgent(exp_config=cfg), visualizer_agent=PlotVisualizer(exp_config=cfg, bridge=bridge), critic_agent=PlotCritic(exp_config=cfg))

def final_plot_review(processor, data):
    """최종 선택 Plot을 추가 코드 생성·실행 없이 검토."""
    field = data['eval_image_field']
    target = review_record(data, field, 'review_failed', {})
    previous = data.get('_latest_review')
    if previous and previous['status'] in ('passed', 'issues_remaining') and all((previous[k] == target[k] for k in ('image_field', 'image_sha256', 'context_sha256'))):
        return {**previous, 'reused_existing_review': True}
    copied = dict(data, current_critic_round=0, target_plot_stylist_desc0=data[field.removesuffix('_base64_jpg')], target_plot_stylist_desc0_base64_jpg=data[field])
    step = {'stage': 'rewrite', 'fields': REWRITE_FIELDS, 'final': True}
    try:
        with review_plan([step]):
            CriticAgent.process(processor.critic_agent, copied, source='stylist')
        value = json.loads(step['response'])
        status = 'passed' if value['critic_suggestions'] == 'No changes needed.' else 'issues_remaining'
        return {**target, 'status': status, 'details': value, 'reused_existing_review': False}
    except Exception as error:
        return {**target, 'status': 'review_failed', 'error_type': type(error).__name__, 'error': str(error)}
