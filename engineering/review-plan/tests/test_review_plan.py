import unittest
from pathlib import Path


SKILL = Path(__file__).parents[1] / "SKILL.md"


class ReviewPlanContractTests(unittest.TestCase):
    def test_skill_uses_a_cost_effective_reviewer_model_with_high_reasoning(self) -> None:
        # Arrange & Act: read the model-facing orchestration contract.
        skill = SKILL.read_text()

        # Assert: reviewer quality and cost are selected by capability, not a fixed model ID.
        self.assertIn("安価側model", skill)
        self.assertIn("reasoning / thinkingは`high`", skill)
        self.assertIn("model名は固定しない", skill)
        self.assertIn("既定model", skill)


if __name__ == "__main__":
    unittest.main()
