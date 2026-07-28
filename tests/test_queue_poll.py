# -*- coding: utf-8 -*-
"""Queue poller battery (order 9N2x9xK) -- the fleet conversion of
W6's Finding-7 doorbell. Formula shape + arm-state default."""
import os
import unittest
from unittest.mock import patch


class TestQueuePoll(unittest.TestCase):
    def test_formula(self):
        import lib.airtable_client as ac
        with patch.dict(os.environ, {"AIRTABLE_TOKEN": "t",
                                     "AIRTABLE_BASE_ID": "b"}), \
             patch.object(ac, "Api"):
            client = ac.AirtableClient()
            client.table.all.return_value = [
                {"id": "recX",
                 "fields": {"Service Instance ID": "A-INTFMT"}}]
            ready = client.list_ready_services()
        self.assertEqual(
            ready, [("recX", {"Service Instance ID": "A-INTFMT"})])
        formula = client.table.all.call_args.kwargs.get("formula") or \
            client.table.all.call_args.args[0]
        self.assertIn("{Status}='Paid'", formula)
        self.assertIn("{Met}=1", formula)
        self.assertIn("-INTFMT", formula)

    def test_formula_failure_returns_empty(self):
        import lib.airtable_client as ac
        with patch.dict(os.environ, {"AIRTABLE_TOKEN": "t",
                                     "AIRTABLE_BASE_ID": "b"}), \
             patch.object(ac, "Api"):
            client = ac.AirtableClient()
            client.table.all.side_effect = RuntimeError("down")
            self.assertEqual(client.list_ready_services(), [])

    def test_arm_state_default(self):
        # Import with the poller explicitly disarmed so no thread
        # spawns under test; then check the shipped default constant.
        with patch.dict(os.environ, {"QUEUE_POLL_ENABLED": "false"}):
            import app
        self.assertEqual(app.QUEUE_POLL_DEFAULT, 'false')
        # exactly-'true' semantics
        with patch.dict(os.environ, {"QUEUE_POLL_ENABLED": "TRUE"}):
            self.assertTrue(app._queue_poll_enabled())
        with patch.dict(os.environ, {"QUEUE_POLL_ENABLED": "yes"}):
            self.assertFalse(app._queue_poll_enabled())


if __name__ == "__main__":
    unittest.main()
