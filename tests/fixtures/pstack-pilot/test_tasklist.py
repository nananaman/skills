from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parent


class TasklistContractTest(unittest.TestCase):
    def test_default_output_keeps_all_tasks_in_input_order(self):
        result = subprocess.run(
            [sys.executable, str(ROOT / "tasklist.py"), str(ROOT / "tasks.json")],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("1: 通知先を確認\n2: 設定を保存\n3: 結果を確認\n", result.stdout)

    def test_listing_does_not_modify_the_input(self):
        source = ROOT / "tasks.json"
        before = source.read_bytes()

        result = subprocess.run(
            [sys.executable, str(ROOT / "tasklist.py"), str(source)],
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(before, source.read_bytes())
