import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).parents[1]
DOCUMENTS = (
    SKILL_DIR / "SKILL.md",
    SKILL_DIR / "references" / "herdr-cli-runbook.md",
)


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


if __name__ == "__main__":
    unittest.main()
