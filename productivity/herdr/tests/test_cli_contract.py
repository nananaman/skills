import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).parents[1]
DOCUMENTS = (
    SKILL_DIR / "SKILL.md",
    SKILL_DIR / "references" / "herdr-cli-runbook.md",
)


def section(content: str, heading: str) -> str:
    start = content.index(heading)
    remainder = content[start + len(heading) :]
    end = remainder.find("\n## ")
    return remainder if end == -1 else remainder[:end]


class HerdrCliContractTest(unittest.TestCase):
    def test_documents_use_v075_wait_commands(self) -> None:
        # Arrange: Both user-facing documents define the supported Herdr workflow.
        content = "\n".join(path.read_text() for path in DOCUMENTS)

        # Act & Assert: Removed top-level waits cannot be copied from the skill.
        self.assertNotIn("herdr wait output", content)
        self.assertNotIn("herdr wait agent-status", content)
        self.assertIn("herdr pane wait-output", content)
        self.assertIn("herdr agent wait", content)

    def test_documents_use_atomic_agent_prompt(self) -> None:
        # Arrange: Prompt submission is a public live-agent CLI contract.
        content = "\n".join(path.read_text() for path in DOCUMENTS)

        # Act & Assert: The removed send command is replaced by atomic prompt submission.
        self.assertNotIn("herdr agent send ", content)
        self.assertIn("herdr agent prompt", content)
        self.assertIn("herdr agent send-keys", content)

    def test_initial_agent_naming_uses_the_current_tab(self) -> None:
        # Arrange: The runbook section is the canonical initial-naming procedure.
        runbook = (SKILL_DIR / "references" / "herdr-cli-runbook.md").read_text()
        initial_naming = section(runbook, "## Agent session の初回命名").split(
            "\n### 基本パターン", 1
        )[0]

        # Act & Assert: Initial naming targets the tab and keeps the pane ID for the agent.
        self.assertIn('["result"]["pane"]["tab_id"]', initial_naming)
        self.assertIn("herdr tab get", initial_naming)
        self.assertIn("herdr tab rename", initial_naming)
        self.assertIn("herdr agent rename \"$CURRENT_PANE\"", initial_naming)
        self.assertNotIn("herdr pane rename", initial_naming)

    def test_initial_agent_naming_preserves_named_tabs(self) -> None:
        # Arrange: Both documents define the generic-agent and tab-label safety boundary.
        skill = (SKILL_DIR / "SKILL.md").read_text()
        runbook = (SKILL_DIR / "references" / "herdr-cli-runbook.md").read_text()
        initial_naming = section(runbook, "## Agent session の初回命名").split(
            "\n### 基本パターン", 1
        )[0]

        # Act & Assert: Only unnamed agents and numeric tabs enter the automatic rename path.
        self.assertIn("`name` がない", skill)
        self.assertIn("番号だけ", skill)
        self.assertIn("非番号", skill)
        self.assertIn("`name` がない", initial_naming)
        self.assertIn(
            "| ASCII の番号だけ | 最初の task label へ rename | 最初の task label |",
            initial_naming,
        )
        self.assertIn(
            "| 非番号 | 変更しない | 既存 tab label |", initial_naming
        )
        self.assertIn("tab rename が失敗したら agent rename へ進まない", initial_naming)

    def test_named_agents_stop_before_tab_label_evaluation(self) -> None:
        # Arrange: Initial naming must reject named agents before inspecting the tab.
        runbook = (SKILL_DIR / "references" / "herdr-cli-runbook.md").read_text()
        initial_naming = section(runbook, "## Agent session の初回命名").split(
            "\n### 基本パターン", 1
        )[0]

        # Act: Locate the ordered safety checks and the first mutating command.
        named_agent_stop = initial_naming.index(
            "`agent get` response に `name` があれば、ここで終了する。"
        )
        tab_label_evaluation = initial_naming.index(
            "`name` がない場合は、tab label から次の分岐を選ぶ。"
        )
        tab_rename = initial_naming.index("herdr tab rename")

        # Assert: A named agent exits before any tab branch can rename the tab.
        self.assertLess(named_agent_stop, tab_label_evaluation)
        self.assertLess(tab_label_evaluation, tab_rename)

    def test_documents_separate_tab_and_pane_label_responsibilities(self) -> None:
        for path in DOCUMENTS:
            with self.subTest(path=path):
                # Arrange: Each user-facing document must expose the safety boundary.
                content = path.read_text()

                # Act & Assert: Tabs identify tasks and only new helper panes get labels.
                self.assertIn("tab label は主タスク", content)
                self.assertIn("pane label は pane 固有", content)
                self.assertIn(
                    "pane label を自動変更できるのは、agent が直前に作成した"
                    "補助 pane だけとする。",
                    content,
                )
                self.assertIn(
                    "人間が管理する既存 pane とその label は変更しない。",
                    content,
                )


if __name__ == "__main__":
    unittest.main()
