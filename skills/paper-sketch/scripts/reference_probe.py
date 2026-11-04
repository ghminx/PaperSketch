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
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from bridge import FileBridge, install_bridge, write_json


async def run(args):
    """실제 참고 pool에서 원본 Retriever·Planner 입력 연결 검증."""
    dataset = args.dataset_dir.resolve()
    manifest = json.loads((dataset / 'reference_manifest.json').read_text(encoding='utf-8'))
    pool = json.loads((dataset / 'ref.json').read_text(encoding='utf-8'))
    if len(pool) != manifest['records']:
        raise ValueError('Prepared reference count differs from manifest')
    install_bridge(FileBridge(args.exchange_dir, timeout=args.timeout))
    from agents.retriever_agent import RetrieverAgent
    from grouped_retriever import GroupedRetrieverAgent
    from agents.planner_agent import PlannerAgent
    cfg = SimpleNamespace(main_model_name='codex-host', temperature=1.0, dataset_dir=dataset)
    data = json.loads(args.input.read_text(encoding='utf-8'))
    data = {'content': data['content'], 'visual_intent': data['visual_intent']}
    retriever = (GroupedRetrieverAgent(exp_config=cfg, groups_dir=args.reference_groups,
                                     audit_path=args.exchange_dir / 'grouped-retrieval.json')
                 if args.retrieval == 'auto' else RetrieverAgent(exp_config=cfg))
    data = await retriever.process(data, retrieval_setting=args.retrieval)
    ids = data['top10_references']
    expected = {r['id']: r for r in (pool[:200] if args.retrieval == 'auto' else pool)}
    if len(ids) != 10 or len(set(ids)) != 10 or any(i not in expected for i in ids):
        raise ValueError('Retriever must return 10 distinct IDs from the active reference pool')
    audit = {'retrieval_mode': args.retrieval, 'dataset_dir': str(dataset),
             'source_ref_sha256': manifest['source_ref_sha256'],
             'candidate_count': len(expected), 'selected_ids': ids,
             'selected_images': [{'id': i, 'sha256': hashlib.sha256(
                 (dataset / expected[i]['path_to_gt_image']).read_bytes()).hexdigest()} for i in ids]}
    write_json(args.exchange_dir / 'retrieval.json', audit)
    if not args.retrieval_only:
        data = await PlannerAgent(exp_config=cfg).process(data)
    write_json(args.exchange_dir / 'result.json', data)
    print(json.dumps({'status': 'complete', 'selected_ids': ids}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset-dir', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--exchange-dir', type=Path, required=True)
    parser.add_argument('--retrieval', choices=['auto', 'random'], default='auto')
    parser.add_argument('--reference-groups', type=Path)
    parser.add_argument('--retrieval-only', action='store_true')
    parser.add_argument('--timeout', type=float, default=1200)
    args = parser.parse_args()
    if args.retrieval == 'auto' and args.reference_groups is None:
        parser.error('auto requires --reference-groups')
    asyncio.run(run(args))
