from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-skill-inventory.py"
SPEC = importlib.util.spec_from_file_location("check_skill_inventory", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SkillInventoryCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "README.md").write_text("# Skills\n", encoding="utf-8")
        (self.root / "engineering").mkdir()
        (self.root / "engineering" / "README.md").write_text("# Engineering\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def add_skill(self, directory: str = "example", name: str = "example") -> Path:
        skill_directory = self.root / "engineering" / directory
        skill_directory.mkdir(parents=True)
        skill = skill_directory / "SKILL.md"
        skill.write_text(
            textwrap.dedent(
                f"""\
                ---
                name: {name}
                description: example skill
                ---

                # Example
                """
            ),
            encoding="utf-8",
        )
        root_readme = self.root / "README.md"
        root_readme.write_text(
            root_readme.read_text(encoding="utf-8") + f"[{name}](./engineering/{directory}/SKILL.md)\n",
            encoding="utf-8",
        )
        category_readme = self.root / "engineering" / "README.md"
        category_readme.write_text(
            category_readme.read_text(encoding="utf-8") + f"[{name}](./{directory}/SKILL.md)\n",
            encoding="utf-8",
        )
        return skill

    def finding_codes(self) -> set[str]:
        _, findings = MODULE.check(self.root)
        return {finding.code for finding in findings}

    def test_accepts_consistent_inventory(self) -> None:
        self.add_skill()

        skills, findings = MODULE.check(self.root)

        self.assertEqual(1, len(skills))
        self.assertEqual([], findings)

    def test_accepts_category_prefixed_name(self) -> None:
        self.add_skill(directory="eventbus", name="engineering-eventbus")

        self.assertEqual(set(), self.finding_codes())

    def test_reports_missing_required_frontmatter(self) -> None:
        skill = self.add_skill()
        skill.write_text("---\nname: example\n---\n", encoding="utf-8")

        self.assertIn("frontmatter-required", self.finding_codes())

    def test_reports_name_directory_mismatch(self) -> None:
        self.add_skill(name="different")

        self.assertIn("name-directory-mismatch", self.finding_codes())

    def test_reports_duplicate_names(self) -> None:
        self.add_skill(directory="first", name="engineering-first")
        self.add_skill(directory="second", name="engineering-first")

        self.assertIn("name-duplicate", self.finding_codes())

    def test_reports_missing_readme_coverage(self) -> None:
        self.add_skill()
        (self.root / "engineering" / "README.md").write_text("# Engineering\n", encoding="utf-8")

        self.assertIn("readme-skill-missing", self.finding_codes())

    def test_reports_missing_relative_link(self) -> None:
        skill = self.add_skill()
        skill.write_text(skill.read_text(encoding="utf-8") + "[missing](./references/missing.md)\n", encoding="utf-8")

        self.assertIn("link-missing", self.finding_codes())

    def test_reports_an_english_control_heading_in_a_skill(self) -> None:
        skill = self.add_skill()
        skill.write_text(skill.read_text(encoding="utf-8") + "\n## Workflow\n", encoding="utf-8")

        self.assertIn("english-control-heading", self.finding_codes())

    def test_reports_an_english_control_heading_in_supporting_markdown(self) -> None:
        skill = self.add_skill()
        reference = skill.parent / "references" / "contract.md"
        reference.parent.mkdir()
        reference.write_text("# 契約\n\n## Completion\n", encoding="utf-8")

        self.assertIn("english-control-heading", self.finding_codes())

    def test_accepts_product_and_technical_headings(self) -> None:
        skill = self.add_skill()
        skill.write_text(
            skill.read_text(encoding="utf-8")
            + "\n## GitHub Tool Routing\n\n## TypeScript / JavaScript\n",
            encoding="utf-8",
        )

        self.assertNotIn("english-control-heading", self.finding_codes())

    def test_ignores_control_headings_inside_code_blocks(self) -> None:
        skill = self.add_skill()
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\n```md\n## Output\n```\n",
            encoding="utf-8",
        )

        self.assertNotIn("english-control-heading", self.finding_codes())

    def test_a_short_fence_does_not_close_a_long_code_block(self) -> None:
        skill = self.add_skill()
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\n````md\n```\n## Output\n````\n",
            encoding="utf-8",
        )

        self.assertNotIn("english-control-heading", self.finding_codes())

    def test_requires_whitespace_before_a_closing_heading_sequence(self) -> None:
        skill = self.add_skill()
        skill.write_text(skill.read_text(encoding="utf-8") + "\n## Output###\n", encoding="utf-8")

        self.assertNotIn("english-control-heading", self.finding_codes())

    def test_accepts_a_closing_heading_sequence_after_whitespace(self) -> None:
        skill = self.add_skill()
        skill.write_text(skill.read_text(encoding="utf-8") + "\n## Output ###\n", encoding="utf-8")

        self.assertIn("english-control-heading", self.finding_codes())

    def test_a_backtick_in_the_info_string_does_not_open_a_code_block(self) -> None:
        skill = self.add_skill()
        skill.write_text(
            skill.read_text(encoding="utf-8") + "\n```foo`bar\n## Output\n",
            encoding="utf-8",
        )

        self.assertIn("english-control-heading", self.finding_codes())

    def test_excludes_readme_and_notice_from_language_check(self) -> None:
        skill = self.add_skill()
        (skill.parent / "README.md").write_text("# Workflow\n", encoding="utf-8")
        (skill.parent / "NOTICE.md").write_text("# Completion\n", encoding="utf-8")

        self.assertNotIn("english-control-heading", self.finding_codes())

    def test_excludes_dependency_directories_from_language_check(self) -> None:
        skill = self.add_skill()
        dependency_doc = skill.parent / "node_modules" / "dependency" / "guide.md"
        dependency_doc.parent.mkdir(parents=True)
        dependency_doc.write_text("# Prerequisites\n", encoding="utf-8")

        self.assertNotIn("english-control-heading", self.finding_codes())


if __name__ == "__main__":
    unittest.main()
