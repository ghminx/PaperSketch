import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from bridge import FileBridge, install_bridge, write_json
from state import load_result, save_result, select_version, summarize_result, validate_completed_turn


def make_processor(dataset: Path, retrieval: str, critic_rounds: int, internal_rounds: int,
                   reference_groups: Path | None = None, retrieval_audit_path: Path | None = None):
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
    await processor.prepare_retrieval([data])
    mode = processor.exp_config.retrieval_setting
    if mode != 'none':
        pool = json.loads((processor.exp_config.dataset_dir / 'ref.json').read_text(encoding='utf-8'))
        active = pool[:200] if mode == 'auto' else pool
        valid = {r['id'] for r in active}
        ids = data['top10_references']
        if len(ids) != 10 or len(set(ids)) != 10 or any(i not in valid for i in ids):
            raise ValueError('Expected ten distinct reference IDs from the active pool')
    data = await processor.process_query_one(data, do_eval=False)
    data['chat_history'] = [{'role': 'assistant', 'content': 'Diagram generated.'}]
    return data


async def refine(processor, data: dict, feedback: str):
    """원본 chat 계약을 유지한 PBInteract 수정 경로 수행."""
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
        data = select_version(await load_result(args.prior), args.image_field)
        await save_result(output, data, action='select', parent=args.prior)
        print(json.dumps({'status': 'complete', 'result': str(output / 'result.json'),
                          'selected_field': data['eval_image_field']}))
        return
    dataset = args.dataset_dir.resolve()
    if args.action == 'generate' and args.retrieval != 'none':
        json.loads((dataset / 'reference_manifest.json').read_text(encoding='utf-8'))
    install_bridge(FileBridge(output / 'requests', timeout=args.timeout))
    processor = make_processor(dataset, args.retrieval, args.critic_rounds, args.internal_rounds,
                               args.reference_groups, output / 'retrieval.json')
    settings = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    settings['host_context_isolation_guaranteed'] = False
    if args.action == 'generate' and args.retrieval == 'auto':
        settings['retrieval_strategy'] = 'grouped-4x6-to10'
    write_json(output / 'run_config.json', settings)
    if args.action == 'generate':
        source = json.loads(args.input.read_text(encoding='utf-8'))
        data = {'content': source['content'], 'visual_intent': source['visual_intent'],
                'additional_info': source.get('additional_info', {'rounded_ratio': '21:9'}),
                'max_critic_rounds': args.critic_rounds}
        data = await generate(processor, data)
    else:
        data = await load_result(args.prior)
        data = await refine(processor, data, args.feedback_file.read_text(encoding='utf-8'))
    await save_result(output, data, action=args.action, parent=args.prior)
    print(json.dumps({'status': 'complete', 'result': str(output / 'result.json'),
                      'image': str(output / 'final.jpg'), 'selected_field': data['eval_image_field']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['generate', 'refine', 'inspect', 'select'])
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
    if args.action == 'generate' and args.retrieval == 'auto' and args.reference_groups is None:
        parser.error('generate --retrieval auto requires --reference-groups')
    if args.action == 'refine' and (args.prior is None or args.feedback_file is None):
        parser.error('refine requires --prior and --feedback-file')
    asyncio.run(run(args))
