"""설치된 파일·데이터·uv 환경의 외부 모델 없는 점검."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory


def verify(root: Path) -> dict:
    """설치 hash·이미지·검색 그룹·원본 import 경로 검증."""
    from PIL import Image

    receipt = json.loads((root / 'installation.json').read_text(encoding='utf-8'))
    for name, expected in receipt['files'].items():
        # 검사 완료 전까지 실행 지침의 자동 발견을 막는 임시 파일 사용
        pending = name == 'SKILL.md' and receipt['status'] == 'installing'
        path = (root / ('SKILL.md.pending' if pending else name)).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f'Installed payload mismatch: {name}')
    if Path(sys.prefix).resolve() != (root / '.venv').resolve():
        raise ValueError('Run this check with the installed .venv Python')
    for vendor in ('interact', 'paperbanana_plot'):
        folder = root / 'assets' / vendor
        manifest = json.loads((folder / 'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
        for name, entry in manifest['files'].items():
            expected = entry if isinstance(entry, str) else entry['vendored_sha256']
            if hashlib.sha256((folder / name).read_bytes()).hexdigest() != expected:
                raise ValueError(f'Vendored source mismatch: {vendor}/{name}')
    counts = {}
    sync = root / 'assets/sync'
    manifest = json.loads((sync / 'SYNC_MANIFEST.json').read_text(encoding='utf-8'))
    for name, entry in manifest['files'].items():
        if hashlib.sha256((sync / name).read_bytes()).hexdigest() != entry['sha256']:
            raise ValueError(f'Synchronous runtime mismatch: {name}')
        if hashlib.sha256((root / entry['source']).read_bytes()).hexdigest() != entry['source_sha256']:
            raise ValueError(f'Synchronous runtime source is stale: {name}')
    for task, count in (('diagram', 298), ('plot', 240)):
        dataset = root / 'data' / task
        rows = json.loads((dataset / 'ref.json').read_text(encoding='utf-8'))
        if len(rows) != count or len({row['id'] for row in rows}) != count:
            raise ValueError(f'Invalid reference count or IDs: {task}')
        for row in rows:
            image = (dataset / row['path_to_gt_image']).resolve()
            if not image.is_relative_to(dataset):
                raise ValueError(f'Reference image outside dataset: {image}')
            with Image.open(image) as opened:
                opened.verify()
        counts[task] = len(rows)
    sys.path.insert(0, str(sync / 'scripts'))
    from bridge import FileBridge, install_bridge
    with TemporaryDirectory(prefix='papersketch-verify-') as temporary:
        install_bridge(FileBridge(Path(temporary)))
        from run import make_processor
        processor = make_processor(root / 'data/diagram', 'auto', 1, 1, root / 'data/diagram/retrieval')
        _, groups, _ = processor.retriever_agent._load_groups()
        from plot_runtime import reference_pool
        reference_pool(root / 'data/plot')
        import agents.planner_agent as diagram_planner
        import paperbanana_plot.agents.planner_agent as plot_planner
        for module in (diagram_planner, plot_planner):
            if not Path(module.__file__).resolve().is_relative_to(root / 'assets'):
                raise ValueError('Agent imported from outside the installed skill')
    return {'status': 'verified_offline', 'runtime': 'synchronous', 'root': str(root), 'python': sys.executable,
            'verified_files': len(receipt['files']), 'references': counts,
            'diagram_group_sizes': [len(rows) for rows, _ in groups],
            'codex_cli': shutil.which('codex'), 'codex_login': 'unverified',
            'imagegen_availability': 'unverified; requires a capable Codex host',
            'model_calls': 0, 'live_generation': 'not_tested'}


if __name__ == '__main__':
    try:
        print(json.dumps(verify(Path(__file__).resolve().parents[1]), ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, ImportError) as error:
        print(f'Installation check failed: {error}', file=sys.stderr)
        sys.exit(1)
