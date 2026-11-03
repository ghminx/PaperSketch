"""설치 대상 제한·기존 파일 보호·실패 시 미완료 스킬 비공개 검증."""
import importlib.util
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('papersketch_installer', ROOT / 'scripts/install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def test_payload_includes_data_and_lock_but_excludes_development_files(self):
        files = installer.payload(ROOT)
        for name in ('SKILL.md', 'pyproject.toml', 'uv.lock', '.python-version',
                     'scripts/run.py', 'scripts/verify_install.py', 'assets/interact/LICENSE',
                     'assets/paperbanana_plot/LICENSE', 'references/plot.md',
                     'data/diagram/ref.json', 'data/diagram/retrieval/manifest.json', 'data/plot/ref.json'):
            self.assertIn(name, files)
        self.assertEqual(sum(name.startswith('data/diagram/images/') for name in files), 298)
        self.assertEqual(sum(name.startswith('data/plot/images/') for name in files), 240)
        self.assertFalse(any(name.startswith(('.git/', '.venv/', 'tests/', 'docs/')) for name in files))
        self.assertNotIn('AGENTS.md', files)
        self.assertFalse(any('__pycache__' in name or name.endswith('.pyc') for name in files))

    def test_plan_does_not_create_destination_and_refuses_existing_directory(self):
        with TemporaryDirectory() as temporary:
            destination = Path(temporary) / 'skill'
            receipt, files = installer.plan(ROOT, destination)
            self.assertFalse(destination.exists())
            self.assertEqual(len(receipt['files']), len(files))
            destination.mkdir()
            marker = destination / 'keep.txt'
            marker.write_text('keep', encoding='utf-8')
            with self.assertRaises(FileExistsError):
                installer.plan(ROOT, destination)
            self.assertEqual(marker.read_text(encoding='utf-8'), 'keep')

    def test_rejects_overlapping_source_destination(self):
        with self.assertRaises(ValueError):
            installer.plan(ROOT, ROOT / 'new-installation')

    def test_failed_environment_setup_preserves_diagnostics_without_publishing_skill(self):
        with TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'source'
            source.mkdir()
            for name in ('SKILL.md', 'pyproject.toml'):
                (source / name).write_text(name, encoding='utf-8')
            files = {path.name: path for path in source.iterdir()}
            receipt = {'destination': str(folder / 'installed'), 'files': {
                name: installer.hashlib.sha256(path.read_bytes()).hexdigest() for name, path in files.items()}}
            with patch.object(installer.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, ['uv'])):
                with self.assertRaises(subprocess.CalledProcessError):
                    installer.install(receipt, files, 'uv')
            destination = folder / 'installed'
            self.assertFalse((destination / 'SKILL.md').exists())
            self.assertTrue((destination / 'SKILL.md.pending').exists())
            self.assertEqual(json.loads((destination / 'installation.json').read_text(encoding='utf-8'))['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
