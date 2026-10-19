import unittest
from actions import build_actions


class BuildActionsTest(unittest.TestCase):
    def test_disabled_actions_keep_input_order(self):
        self.assertEqual(
            build_actions(["保存", "戻る"], is_disabled=True),
            [{"label": "保存", "disabled": True}, {"label": "戻る", "disabled": True}],
        )

    def test_default_actions_are_enabled(self):
        self.assertEqual(build_actions(["保存"]), [{"label": "保存", "disabled": False}])

    def test_empty_input_has_no_actions(self):
        self.assertEqual(build_actions([]), [])
