# BEGIN_SYNC_ENTRY
# CLI는 동기 실행 사본 사용, 아래 원본 함수는 회귀 비교용 보존
if __name__ == '__main__':
    import runpy
    import sys
    from pathlib import Path
    entry = Path(__file__).resolve().parents[1] / 'assets/sync/scripts' / Path(__file__).name
    sys.path.insert(0, str(entry.parent))
    runpy.run_path(str(entry), run_name='__main__')
    raise SystemExit(0)
# END_SYNC_ENTRY
import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from bridge import FileBridge, install_bridge, write_json
from state import load_result, save_result, save_failed_result, select_version, summarize_result, validate_completed_turn
from execution import begin_execution, retrieval_started, retrieval_completed, finish_execution


def make_processor(dataset: Path, retrieval: str, critic_rounds: int, internal_rounds: int,
                   reference_groups: Path | None = None, retrieval_audit_path: Path | None = None,
                   *, guard_reviews: bool = True):
    """보존된 원본 agent와 processor 구성."""
    from agents.critic_agent import CriticAgent
    from agents.planner_agent import PlannerAgent
    from agents.stylist_agent import StylistAgent
    from agents.retriever_agent import RetrieverAgent
    from grouped_retriever import GroupedRetrieverAgent
    from agents.visualizer_agent import VisualizerAgent
    from agents.vanilla_agent import VanillaAgent
    from agents.polish_agent import PolishAgent
    from agents.refiner.pb_interact import PBInteract
    if guard_reviews:
        from review_agents import ValidatedCriticAgent as CriticAgent, ValidatedPBInteract as PBInteract
    from utils.paperviz_processor import PaperVizProcessor
    cfg = SimpleNamespace(dataset_dir=dataset.resolve(),
                          work_dir=Path(__file__).resolve().parents[1] / 'assets/interact',
                          main_model_name='codex-host', image_gen_model_name='codex-image-host',
                          temperature=1.0, exp_mode='demo_full', retrieval_setting=retrieval,
                          max_critic_rounds=critic_rounds, refiner='pb_interact',
                          refiner_internal_critic_rounds=internal_rounds, concurrent_num=1)
    return PaperVizProcessor(
        exp_config=cfg, vanilla_agent=VanillaAgent(exp_config=cfg),
        planner_agent=PlannerAgent(exp_config=cfg), stylist_agent=StylistAgent(exp_config=cfg),
        retriever_agent=(GroupedRetrieverAgent(exp_config=cfg, groups_dir=reference_groups,
                                             audit_path=retrieval_audit_path)
                         if retrieval == 'auto' else RetrieverAgent(exp_config=cfg)),
        visualizer_agent=VisualizerAgent(exp_config=cfg),
        critic_agent=CriticAgent(exp_config=cfg), polish_agent=PolishAgent(exp_config=cfg),
        refiner_agent=PBInteract(exp_config=cfg))


async def generate(processor, data: dict):
    """원본 검색 준비·full 생성 경로 수행."""
    retrieval_started(data)
    await processor.prepare_retrieval([data])
    mode = processor.exp_config.retrieval_setting
    if mode != 'none':
        pool = json.loads((processor.exp_config.dataset_dir / 'ref.json').read_text(encoding='utf-8'))
        active = pool[:200] if mode == 'auto' else pool
        valid = {r['id'] for r in active}
        ids = data['top10_references']
        if len(ids) != 10 or len(set(ids)) != 10 or any(i not in valid for i in ids):
            raise ValueError('Expected ten distinct reference IDs from the active pool')
    retrieval_completed(data, mode, processor.exp_config.dataset_dir)
    data = await processor.process_query_one(data, do_eval=False)
    data['chat_history'] = [{'role': 'assistant', 'content': 'Diagram generated.'}]
    return data


async def refine(processor, data: dict, feedback: str):
    """원본 chat 계약을 유지한 PBInteract 수정 경로 수행."""
    if data.get('task_name') == 'plot':
        raise ValueError('Plot PBInteract refinement is not connected; generate a new plot instead')
    if not feedback.strip():
        raise ValueError('Feedback must not be empty')
    validate_completed_turn(data)
    data['chat_history'] = data['chat_history'] + [{'role': 'user', 'content': feedback}]
    data = await processor.process_single_feedback(data, simulate_user=False, do_eval=False)
    data['chat_history'].append({'role': 'assistant', 'content': 'Diagram revision processed.'})
    return data


async def run(args):
    """생성·피드백 수정·저장 결과 조회·선택의 CLI 경로 수행."""
    if args.action == 'inspect':
        print(json.dumps(summarize_result(await load_result(args.prior)), ensure_ascii=False))
        return
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f'Use a new output directory: {output}')
    if args.critic_rounds < 0 or args.internal_rounds < 1:
        raise ValueError('critic-rounds must be >=0 and internal-rounds must be >=1')
    if args.action == 'select':
        data = await load_result(args.prior)
        begin_execution(args, data, parent=args.prior)
        data = select_version(data, args.image_field)
        finish_execution(data, [], 'complete')
        await save_result(output, data, action='select', parent=args.prior)
        print(json.dumps({'status': 'complete', 'result': str(output / 'result.json'),
                          'selected_image_ratio': summarize_result(data)['selected_image_ratio'],
                          'final_review': summarize_result(data)['final_review'],
                          'execution': data['execution_record'],
                          'selected_field': data['eval_image_field']}))
        return
    if args.task == 'plot':
        if args.plot_timeout <= 0:
            raise ValueError('plot-timeout must be positive')
        from run_plot import run_plot
        return await run_plot(args)
    dataset = args.dataset_dir.resolve()
    if args.action == 'generate' and args.retrieval != 'none':
        json.loads((dataset / 'reference_manifest.json').read_text(encoding='utf-8'))
    bridge = FileBridge(output / 'requests', timeout=args.timeout, independent_text=args.action == 'refine')
    install_bridge(bridge)
    processor = make_processor(dataset, args.retrieval, args.critic_rounds, args.internal_rounds,
                               args.reference_groups, output / 'retrieval.json')
    requested = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    settings = {'format_version': 2, 'requested_options': requested, 'execution_policy': {
        'text_host': 'independent-codex' if args.action == 'refine' else 'per-request',
        'final_review_text_host': 'independent-codex', 'expected_image_tool': 'imagegen',
        'review_validation_enabled': True, 'review_response_attempts': 2, 'final_review': 'read_only'}}
    write_json(output / 'run_config.json', settings)
    data = {}
    begin_execution(args, data)
    try:
        if args.action == 'generate':
            source = json.loads(args.input.read_text(encoding='utf-8'))
            data.update({'content': source['content'], 'visual_intent': source['visual_intent'],
                    'additional_info': source.get('additional_info', {'rounded_ratio': '21:9'}),
                    'max_critic_rounds': args.critic_rounds})
            data['requested_image_ratio'] = data['additional_info'].get('rounded_ratio', '1:1')
            data = await generate(processor, data)
        else:
            data = await load_result(args.prior)
            begin_execution(args, data, parent=args.prior)
            data = await refine(processor, data, args.feedback_file.read_text(encoding='utf-8'))
        if not data.get(data['eval_image_field']):
            valid = [k for k, v in data.items() if k.endswith('_base64_jpg') and v]
            if not valid:
                raise RuntimeError('Image generation failed: no valid image is available')
            data['eval_image_field'] = valid[-1]
            data['selection_fallback_reason'] = 'Selected render unavailable; retained last valid image'
        from review_agents import final_review
        data['final_review'] = await final_review(processor, data, args.action)
    except Exception as error:
        # 실행 경계에서 중간 결과를 보존한 뒤 원래 예외 의미 유지
        for call in bridge.image_calls:
            if call['status'] == 'running':
                call.update(status='aborted', error=str(error))
        if bridge.image_calls:
            write_json(output / 'requests/image_generation.json', bridge.image_calls)
        data.setdefault('image_generation_history', []).extend(bridge.image_calls)
        data['review_validation_history'] = bridge.review_calls
        if bridge.review_calls and bridge.review_calls[-1]['status'] != 'valid':
            data['final_review'] = {'status': 'review_failed', 'error_type': type(error).__name__,
                                    'error': str(error), 'reason': 'Review failed before completion'}
        finish_execution(data, bridge.request_paths, 'failed')
        await save_failed_result(output, data, error)
        raise
    data.setdefault('image_generation_history', []).extend(bridge.image_calls)
    failed = sum(c['status'] != 'succeeded' for c in bridge.image_calls)
    status = 'completed_with_image_failures' if failed else 'complete'
    data['image_generation_status'] = status
    data['review_validation_history'] = bridge.review_calls
    if data['final_review']['status'] == 'review_failed':
        status = 'completed_with_review_failure'
    elif data['final_review']['status'] == 'issues_remaining' and status == 'complete':
        status = 'completed_with_issues'
    finish_execution(data, bridge.request_paths, status)
    await save_result(output, data, action=args.action, parent=args.prior)
    print(json.dumps({'status': status, 'image_failures': failed, 'result': str(output / 'result.json'),
                      'image_generation_status': data['image_generation_status'],
                      'selected_image_ratio': summarize_result(data)['selected_image_ratio'],
                      'final_review': summarize_result(data)['final_review'],
                      'execution': data['execution_record'],
                      'image': str(output / 'final.jpg'), 'selected_field': data['eval_image_field']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['generate', 'refine', 'inspect', 'select'])
    parser.add_argument('--task', choices=['diagram', 'plot'], default='diagram')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--dataset-dir', type=Path)
    parser.add_argument('--input', type=Path)
    parser.add_argument('--prior', type=Path)
    parser.add_argument('--feedback-file', type=Path)
    parser.add_argument('--image-field')
    parser.add_argument('--retrieval', choices=['auto', 'random', 'none'], default='auto')
    parser.add_argument('--reference-groups', type=Path)
    parser.add_argument('--critic-rounds', type=int, default=3)
    parser.add_argument('--internal-rounds', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=1200)
    parser.add_argument('--plot-timeout', type=float, default=30)
    args = parser.parse_args()
    if args.action != 'inspect' and args.output is None:
        parser.error('generate/refine/select require --output')
    if args.action in ('generate', 'refine') and args.dataset_dir is None:
        parser.error('generate/refine require --dataset-dir')
    if args.action in ('refine', 'inspect', 'select') and args.prior is None:
        parser.error('refine/inspect/select require --prior')
    if args.action == 'select' and args.image_field is None:
        parser.error('select requires --image-field')
    if args.action == 'generate' and args.input is None:
        parser.error('generate requires --input')
    if args.action == 'generate' and args.task == 'diagram' and args.retrieval == 'auto' and args.reference_groups is None:
        parser.error('generate --retrieval auto requires --reference-groups')
    if args.action == 'refine' and (args.prior is None or args.feedback_file is None):
        parser.error('refine requires --prior and --feedback-file')
    from startup_check import require_asyncio
    import sys
    require_asyncio(stream=sys.stderr)
    asyncio.run(run(args))
