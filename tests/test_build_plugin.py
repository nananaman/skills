from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / 'scripts/build-plugin.py'


class BuildPluginTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / 'source'
        self.root.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True)
        (self.root / 'plugin').mkdir()
        (self.root / 'plugin/plugin.json').write_text(json.dumps({
            '$schema': 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
            'name': 'test-skills', 'version': '0.1.0', 'description': 'Test skills',
        }))
        (self.root / 'plugin/README.md').write_text('# Package\n')
        for category, directory, name in [('engineering', 'first', 'first'),
                                           ('provider', 'second', 'provider-second')]:
            skill = self.root / category / directory
            skill.mkdir(parents=True)
            (skill / 'SKILL.md').write_text(
                f'---\nname: {name}\ndescription: Test skill\n---\n')
        (self.root / 'engineering/first/SKILL.md').write_text(
            '---\nname: first\ndescription: Test skill\n---\n'
            '[Other](../../provider/second/SKILL.md#contract)\n')
        (self.root / 'engineering/first/run.py').write_text('print("example")\n')
        (self.root / 'engineering/first/run.py').chmod(0o755)
        self.track()
        self.output = Path(self.temp.name) / 'output'

    def tearDown(self):
        self.temp.cleanup()

    def track(self):
        subprocess.run(['git', '-C', str(self.root), 'add', '.'], check=True)

    def build(self):
        return subprocess.run(['python3', str(SCRIPT), '--root', str(self.root),
                               '--output', str(self.output)], text=True, capture_output=True)

    def test_zip_contains_all_skills_resources_and_resolving_cross_skill_links(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        with zipfile.ZipFile(self.output / 'test-skills-0.1.0.zip') as archive:
            skills = {name for name in archive.namelist() if name.endswith('/SKILL.md')}
            self.assertEqual(skills, {'test-skills/skills/first/SKILL.md',
                                      'test-skills/skills/provider-second/SKILL.md'})
            self.assertIn(b'../provider-second/SKILL.md#contract',
                          archive.read('test-skills/skills/first/SKILL.md'))
            self.assertEqual(archive.read('test-skills/skills/first/run.py'), b'print("example")\n')
            self.assertTrue(archive.getinfo('test-skills/skills/first/run.py').external_attr >> 16 & 0o111)
            self.assertNotIn('test-skills/AGENTS.md', archive.namelist())
        inventory = json.loads((self.output / 'test-skills/inventory.json').read_text())
        self.assertEqual({item['name'] for item in inventory['skills']}, {'first', 'provider-second'})

    def test_untracked_private_file_is_not_packaged(self):
        (self.root / 'engineering/first/private.json').write_text('private')
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.output / 'test-skills/skills/first/private.json').exists())

    def test_untracked_skill_cannot_be_silently_omitted(self):
        skill = self.root / 'new/skill/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: new\ndescription: Example\n---\n')
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('untracked SKILL.md', result.stderr)

    def test_link_to_unbundled_file_is_rejected(self):
        skill = self.root / 'engineering/first/SKILL.md'
        skill.write_text(skill.read_text() + '[Private](../../private.md)\n')
        (self.root / 'private.md').write_text('Private')
        self.track()
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('unbundled link', result.stderr)

    def test_tracked_symlink_cannot_read_private_target(self):
        private = Path(self.temp.name) / 'private.txt'
        private.write_text('Private')
        (self.root / 'engineering/first/secret').symlink_to(private)
        self.track()
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('symlink', result.stderr)

    def test_existing_output_is_preserved(self):
        self.output.mkdir()
        sentinel = self.output / 'keep.txt'
        sentinel.write_text('Keep')
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(sentinel.read_text(), 'Keep')


if __name__ == '__main__':
    unittest.main()
