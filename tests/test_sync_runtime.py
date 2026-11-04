"""원본 보존·동기 실행 사본 무결성·프롬프트 동일성 검증."""
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import unittest

SKILL = Path(__file__).resolve().parents[1] / 'skills/paper-sketch'
SYNC = SKILL / 'assets/sync'


class SyncRuntimeTests(unittest.TestCase):
    def test_public_cli_help_does_not_dispatch_recursively(self):
        result = subprocess.run([sys.executable, '-B', str(SKILL / 'scripts/run.py'), '--help'],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8'))
        self.assertIn(b'--critic-rounds', result.stdout)

    def test_snapshots_and_converted_runtime_match_their_manifests(self):
        manifest = json.loads((SYNC / 'SYNC_MANIFEST.json').read_text(encoding='utf-8'))
        for name, entry in manifest['files'].items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((SYNC / name).read_bytes()).hexdigest(), entry['sha256'])
                self.assertEqual(hashlib.sha256((SKILL / entry['source']).read_bytes()).hexdigest(), entry['source_sha256'])

    def test_executable_agents_and_adapters_have_no_async_or_event_loop(self):
        for path in SYNC.rglob('*.py'):
            if 'style_guides' in path.parts:
                continue
            with self.subTest(file=str(path)):
                tree = ast.parse(path.read_text(encoding='utf-8'))
                self.assertFalse(any(isinstance(n, (ast.AsyncFunctionDef, ast.Await, ast.AsyncFor, ast.AsyncWith)) for n in ast.walk(tree)))
                self.assertFalse(any(isinstance(n, ast.Name) and n.id in ('asyncio', 'aiofiles') for n in ast.walk(tree)))

    def test_all_agent_prompt_constants_keep_original_values(self):
        found = 0
        for vendor in ('interact', 'paperbanana_plot'):
            for original in (SKILL / 'assets' / vendor / 'agents').rglob('*.py'):
                converted = SYNC / original.relative_to(SKILL)
                def constants(path):
                    result = {}
                    for node in ast.parse(path.read_text(encoding='utf-8')).body:
                        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                            for target in node.targets:
                                if isinstance(target, ast.Name) and 'PROMPT' in target.id:
                                    result[target.id] = node.value.value
                    return result
                expected = constants(original)
                self.assertEqual(constants(converted), expected)
                found += len(expected)
        self.assertGreaterEqual(found, 10)


if __name__ == '__main__':
    unittest.main()
