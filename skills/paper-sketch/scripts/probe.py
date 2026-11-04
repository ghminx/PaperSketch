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


async def run(args):
    """원본 agent의 단일 호출 또는 생성·검토 왕복 연결 검증."""
    install_bridge(FileBridge(args.exchange_dir, timeout=args.timeout))
    config = SimpleNamespace(main_model_name='codex-host',
                             image_gen_model_name='codex-image-host', temperature=1.0)
    data = {'content': 'Input observations pass through an encoder and then a predictor.',
            'visual_intent': 'A three-stage scientific method diagram.',
            'top10_references': [], 'retrieved_examples': [],
            'additional_info': {'rounded_ratio': '16:9'}}
    if args.kind in ('planner', 'roundtrip'):
        from agents.planner_agent import PlannerAgent
        result = await PlannerAgent(exp_config=config).process(data)
        if args.kind == 'roundtrip':
            from agents.visualizer_agent import VisualizerAgent
            from agents.critic_agent import CriticAgent
            result = await VisualizerAgent(exp_config=config).process(result)
            result['current_critic_round'] = 0
            result = await CriticAgent(exp_config=config).process(result, source='planner')
    else:
        from agents.visualizer_agent import VisualizerAgent
        data['target_diagram_desc0'] = 'Three boxes: observations, encoder, predictor; arrows left to right.'
        result = await VisualizerAgent(exp_config=config).process(data)
    write_json(args.exchange_dir / 'result.json', result)
    print(json.dumps({'status': 'complete', 'result': str(args.exchange_dir / 'result.json')}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--exchange-dir', type=Path, required=True)
    parser.add_argument('--kind', choices=['planner', 'visualizer', 'roundtrip'], default='planner')
    parser.add_argument('--timeout', type=float, default=300)
    asyncio.run(run(parser.parse_args()))
