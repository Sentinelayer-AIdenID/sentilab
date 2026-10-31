"""Worker cleanup must not signal a numeric group after its owner is reaped."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from sentilab_core.execution import recorded_call
from sentilab_core.operations import Context


class WorkerIdentityTests(unittest.IsolatedAsyncioTestCase):
    async def test_completed_workers_never_signal_a_reusable_process_group(self):
        with tempfile.TemporaryDirectory() as directory:
            context = Context(Path(directory), {})
            # Real workers exit and are reaped by communicate(). Their numeric
            # PID/PGID no longer proves ownership, regardless of result validity.
            with patch("sentilab_core.execution.os.killpg") as signal_group:
                result = await recorded_call(context, "chiplet.build", {"fixture": "plate"})
                self.assertEqual(result["fixture"], "plate")
                signal_group.assert_not_called()
            with patch("sentilab_core.execution.os.killpg") as signal_group:
                with self.assertRaises(ValueError):
                    await recorded_call(context, "chiplet.build", {"fixture": "unknown"})
                signal_group.assert_not_called()


if __name__ == "__main__":
    unittest.main()
