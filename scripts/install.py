"""개발 저장소에서 실행에 필요한 파일·데이터·uv 환경만 독립 설치."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys


def payload(source: Path) -> dict[str, Path]:
    """설치 대상 경로와 원본 파일의 명시적 대응 구성."""
    skill = source / 'skills/paper-sketch'
    files = {'SKILL.md': skill / 'SKILL.md'}
    for name in ('pyproject.toml', 'uv.lock', '.python-version'):
        files[name] = source / name
    for directory, prefix in [(skill / name, name) for name in ('scripts', 'assets', 'references')] + [(source / 'data', 'data')]:
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        for path in sorted(directory.rglob('*')):
            if path.is_symlink() or (os.name == 'nt' and path.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError(f'Linked payload paths are not supported: {path}')
            if '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo'):
                continue
            if path.is_file():
                files[f'{prefix}/{path.relative_to(directory).as_posix()}'] = path
    for path in files.values():
        if not path.is_file() or not path.resolve().is_relative_to(source):
            raise ValueError(f'Missing or external payload file: {path}')
    return files


def plan(source: Path, destination: Path) -> tuple[dict, dict[str, Path]]:
    """기존 설치 보존 및 복사 범위·용량·hash 계산."""
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f'Destination already exists; keep it and choose a new path: {destination}')
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Source and destination must be separate directories')
    files = payload(source)
    return {'format_version': 1, 'source': str(source), 'destination': str(destination),
            'files': {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()},
            'payload_bytes': sum(path.stat().st_size for path in files.values()),
            'environment': 'uv sync --locked --no-dev --python 3.11',
            'excluded': ['.git', 'tests', 'docs', 'AGENTS.md', 'development .venv', 'runs', 'outputs'],
            'external_operations': ['uv package downloads; Python 3.11 download if unavailable'],
            'model_calls': False}, files


def install(receipt: dict, files: dict[str, Path], uv: str) -> None:
    """새 폴더에 복사·환경 구성·오프라인 검사 후 스킬 공개."""
    destination = Path(receipt['destination'])
    destination.mkdir(parents=True, exist_ok=False)
    marker = destination / 'installation.json'
    receipt['status'] = 'installing'
    marker.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    environment = os.environ.copy()
    environment.pop('PYTHONPATH', None)
    environment.pop('PYTHONHOME', None)
    environment.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
                       UV_PROJECT_ENVIRONMENT=str(destination / '.venv'))
    try:
        for name, source in files.items():
            target = destination / ('SKILL.md.pending' if name == 'SKILL.md' else name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            if hashlib.sha256(target.read_bytes()).hexdigest() != receipt['files'][name]:
                raise ValueError(f'Payload changed during installation: {name}')
        subprocess.run([uv, 'sync', '--locked', '--no-dev', '--python', '3.11', '--project', str(destination)],
                       cwd=destination, env=environment, check=True)
        python = destination / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        subprocess.run([str(python), '-B', str(destination / 'scripts/verify_install.py')],
                       cwd=destination, env=environment, check=True)
        (destination / 'SKILL.md.pending').rename(destination / 'SKILL.md')
    except (OSError, ValueError, subprocess.SubprocessError):
        # 실패 환경은 진단용으로 보존하고 미완료 스킬의 자동 발견 방지
        if (destination / 'SKILL.md').exists():
            (destination / 'SKILL.md').rename(destination / 'SKILL.md.pending')
        receipt['status'] = 'failed'
        marker.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
        raise
    receipt['status'] = 'installed'
    marker.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Installed: {destination}', flush=True)
    print('Restart Codex or start a new chat to discover paper-sketch. No model call was made.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--dest', type=Path, default=Path.home() / '.agents/skills/paper-sketch')
    parser.add_argument('--apply', action='store_true', help='Install; otherwise only print the plan')
    args = parser.parse_args()
    receipt, files = plan(args.source.expanduser().resolve(), args.dest.expanduser().resolve())
    print(json.dumps({k: v for k, v in receipt.items() if k != 'files'} | {'file_count': len(files)},
                     ensure_ascii=False, indent=2), flush=True)
    if args.apply:
        uv = shutil.which('uv')
        if uv is None:
            raise FileNotFoundError('uv is required; install it using https://docs.astral.sh/uv/getting-started/installation/')
        install(receipt, files, uv)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(f'Installation failed: {error}', file=sys.stderr)
        sys.exit(1)
