"""보존된 원본·연결 코드로부터 순차 동기 실행 사본 생성."""
import ast
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/paper-sketch'
TARGET = SKILL / 'assets/sync'


def canonical_source(text):
    """원본 비교에 불필요한 CLI 동기 분기만 제거."""
    return re.sub(r'# BEGIN_SYNC_ENTRY\r?\n.*?# END_SYNC_ENTRY\r?\n', '', text, flags=re.S)


class Sequential(ast.NodeTransformer):
    """await 순서·인자·분기를 유지하고 실행 대기만 동기 연산으로 변경."""
    def visit_AsyncFunctionDef(self, node):
        self.generic_visit(node)
        return ast.copy_location(ast.FunctionDef(name=node.name, args=node.args, body=node.body,
            decorator_list=node.decorator_list, returns=node.returns, type_comment=node.type_comment), node)

    def visit_Await(self, node):
        return self.visit(node.value)

    def visit_AsyncWith(self, node):
        self.generic_visit(node)
        return ast.copy_location(ast.With(items=node.items, body=node.body, type_comment=node.type_comment), node)

    def visit_AsyncFor(self, node):
        self.generic_visit(node)
        return ast.copy_location(ast.For(target=node.target, iter=node.iter, body=node.body,
            orelse=node.orelse, type_comment=node.type_comment), node)

    def visit_Import(self, node):
        node.names = [alias for alias in node.names if alias.name not in ('asyncio', 'aiofiles', 'aiofiles.os')]
        return node if node.names else None

    def visit_ImportFrom(self, node):
        if node.module == 'startup_check':
            return None
        if node.module == 'tqdm.asyncio':
            node.module = 'tqdm'
        return node

    def visit_Expr(self, node):
        if isinstance(node.value, ast.Call) and ast.unparse(node.value.func) == 'require_asyncio':
            return None
        return self.generic_visit(node)

    def visit_Call(self, node):
        self.generic_visit(node)
        name = ast.unparse(node.func)
        if name == 'asyncio.run' or name == 'asyncio.create_task':
            return node.args[0]
        if name == 'asyncio.to_thread':
            return ast.copy_location(ast.Call(func=node.args[0], args=node.args[1:], keywords=node.keywords), node)
        if name == 'loop.run_in_executor':
            return ast.copy_location(ast.Call(func=node.args[1], args=node.args[2:], keywords=node.keywords), node)
        if name == 'asyncio.get_running_loop':
            return ast.copy_location(ast.Name(id='time', ctx=ast.Load()), node)
        if name == 'loop.time':
            node.func = ast.parse('time.monotonic', mode='eval').body
        elif name == 'asyncio.sleep':
            node.func = ast.parse('time.sleep', mode='eval').body
        elif name == 'asyncio.Semaphore':
            node.func = ast.parse('threading.Semaphore', mode='eval').body
        elif name == 'asyncio.as_completed':
            return node.args[0]
        elif name in ('asyncio.gather', 'tqdm.gather'):
            if len(node.args) != 1 or not isinstance(node.args[0], ast.Starred):
                raise ValueError('Unexpected gather contract')
            return ast.copy_location(ast.Call(func=ast.Name(id='list', ctx=ast.Load()),
                args=[node.args[0].value], keywords=[]), node)
        return node

    def visit_Attribute(self, node):
        self.generic_visit(node)
        name = ast.unparse(node)
        if name.startswith('aiofiles.os.'):
            return ast.copy_location(ast.parse(name.replace('aiofiles.os.', 'os.', 1), mode='eval').body, node)
        if name == 'aiofiles.open':
            return ast.copy_location(ast.Name(id='open', ctx=ast.Load()), node)
        return node


def convert(raw: bytes) -> bytes:
    """라이선스·문자열 값 보존 후 실행 AST의 동기 변환 수행."""
    source = canonical_source(raw.decode('utf-8'))
    original = ast.parse(source)
    if not original.body:
        return raw
    header = '\n'.join(source.splitlines()[:original.body[0].lineno - 1])
    tree = Sequential().visit(original)
    ast.fix_missing_locations(tree)
    # 원본 문자열·docstring보다 앞에 import를 넣지 않도록 마지막에 삽입
    index = 1 if isinstance(tree.body[0], ast.Expr) and isinstance(tree.body[0].value, ast.Constant) else 0
    while index < len(tree.body) and isinstance(tree.body[index], ast.ImportFrom) and tree.body[index].module == '__future__':
        index += 1
    tree.body[index:index] = [ast.Import(names=[ast.alias(name='time')]), ast.Import(names=[ast.alias(name='threading')])]
    return (header + '\n' + ast.unparse(tree) + '\n').encode('utf-8')


def build():
    """원본 hash·변환 결과 hash를 함께 보존하는 실행 사본 생성."""
    manifest = {'version': 1, 'description': 'Sequential synchronous conversion; public prompts and agent ordering preserved', 'files': {}}
    sources = []
    for name in ('interact', 'paperbanana_plot'):
        for path in sorted((SKILL / 'assets' / name).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
                sources.append((path, f'assets/{name}/{path.relative_to(SKILL / "assets" / name).as_posix()}'))
    for path in sorted((SKILL / 'scripts').glob('*.py')):
        if path.name != 'startup_check.py':
            sources.append((path, 'scripts/' + path.name))
    for source, name in sources:
        raw = source.read_bytes()
        copied = convert(raw) if source.suffix == '.py' and 'style_guides' not in source.parts else raw
        destination = TARGET / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(copied)
        manifest['files'][name] = {'source': source.relative_to(SKILL).as_posix(),
            'source_sha256': hashlib.sha256(raw).hexdigest(), 'sha256': hashlib.sha256(copied).hexdigest()}
    # 원본 manifest는 원본 사본에 유지하고 실행 사본에는 실제 변환 hash 기록
    for name in ('interact', 'paperbanana_plot'):
        path = TARGET / 'assets' / name / 'SOURCE_MANIFEST.json'
        source = json.loads(path.read_text(encoding='utf-8'))
        source['upstream_files'] = source['files']
        source['files'] = {key: hashlib.sha256((path.parent / key).read_bytes()).hexdigest() for key in source['files']}
        source['execution'] = 'synchronous; source snapshots remain in the outer assets directory'
        path.write_text(json.dumps(source, ensure_ascii=False, indent=2), encoding='utf-8')
        manifest['files'][path.relative_to(TARGET).as_posix()]['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    (TARGET / 'SYNC_MANIFEST.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Built {len(manifest["files"])} synchronous runtime files: {TARGET}')


if __name__ == '__main__':
    build()
