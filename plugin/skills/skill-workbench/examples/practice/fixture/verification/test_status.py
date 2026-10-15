import unittest
from status import status_label


class StatusLabelTest(unittest.TestCase):
    def test_queued_request_is_preparing(self):
        self.assertEqual(status_label(True), "準備中")

    def test_accepted_request_is_accepted(self):
        self.assertEqual(status_label(False), "受付済み")
