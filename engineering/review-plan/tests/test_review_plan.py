import unittest
from pathlib import Path


SKILL = Path(__file__).parents[1] / "SKILL.md"


class ReviewPlanContractTests(unittest.TestCase):
    def test_skill_uses_a_cost_effective_reviewer_model_with_high_reasoning(self) -> None:
        # Arrange & Act: read the model-facing orchestration contract.
        skill = SKILL.read_text()

        # Assert: reviewer quality and cost are selected by capability, not a fixed model ID.
        self.assertIn("安価な側のモデル", skill)
        self.assertIn("推論強度は`high`", skill)
        self.assertIn("モデル名は固定しない", skill)
        self.assertIn("既定モデル", skill)


if __name__ == "__main__":
    unittest.main()
