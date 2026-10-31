"""Production configuration with real service signing and runtime test pins."""
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from sundai_controller import trust
from sentilab_core.ledger import Ledger, replay
from sentilab_core.operations import environment_context
from sentilab_core.test_ledger import run_record


class EnvironmentContextTests(unittest.TestCase):
    def setUp(self):
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ("SENTILAB_VIEW_PUBLIC_KEYS", "SENTILAB_SIGNER_FACTORY", "SENTILAB_LIVE_DIR"):
            os.environ.pop(name, None)
        seed = os.urandom(32)
        self.identity = Ed25519PrivateKey.from_private_bytes(seed)
        os.environ["FLIGHT_SIGNING_SEED_B64"] = base64.b64encode(seed).decode()
        self.public_bytes = self.identity.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        self.key_id = "sha256:" + hashlib.sha256(self.public_bytes).hexdigest()
        pins = mock.patch.object(trust, "PINNED_SERVICE_KEYS", {self.key_id: self.public_bytes.hex()})
        pins.start()
        self.addCleanup(pins.stop)

    def test_unset_override_uses_shared_public_registry_without_loading_seed(self):
        os.environ["SENTILAB_LIVE_DIR"] = "/tmp/test-live-storage"
        os.environ.pop("FLIGHT_SIGNING_SEED_B64")
        context = environment_context()
        self.assertEqual(context.public_keys, {self.key_id: self.public_bytes})
        self.assertIsNone(context.signer)
        self.assertEqual(context.root, Path("/tmp/test-live-storage"))

    def test_explicit_override_replaces_registry_even_when_empty(self):
        os.environ.pop("FLIGHT_SIGNING_SEED_B64")
        for override in ({"override": self.public_bytes.hex()}, {}):
            with self.subTest(override_names=list(override)):
                os.environ["SENTILAB_VIEW_PUBLIC_KEYS"] = json.dumps(override)
                context = environment_context()
                self.assertEqual(context.public_keys, {name: bytes.fromhex(value) for name, value in override.items()})

    def test_empty_environment_value_is_invalid_not_a_registry_fallback(self):
        os.environ["SENTILAB_VIEW_PUBLIC_KEYS"] = ""
        with self.assertRaises(ValueError):
            environment_context()

    def test_production_factory_matches_shared_pin_and_signs(self):
        os.environ["SENTILAB_SIGNER_FACTORY"] = "sentilab_core.signing:service_signer"
        context = environment_context()
        self.assertEqual(context.public_keys[context.signer.key_id], context.signer.public_key)
        payload = b"shared service identity"
        self.identity.public_key().verify(context.signer.sign(payload), payload)

    def test_factory_cannot_fall_back_to_registry_when_override_excludes_it(self):
        os.environ["SENTILAB_SIGNER_FACTORY"] = "sentilab_core.signing:service_signer"
        for override in ({}, {self.key_id: bytes(reversed(self.public_bytes)).hex()}):
            with self.subTest(override_names=list(override)):
                os.environ["SENTILAB_VIEW_PUBLIC_KEYS"] = json.dumps(override)
                with self.assertRaisesRegex(ValueError, "does not match operator trust pin"):
                    environment_context(ephemeral=True)

    def test_explicit_ephemeral_demo_does_not_require_shared_registry(self):
        os.environ.pop("FLIGHT_SIGNING_SEED_B64")
        with mock.patch.object(trust, "PINNED_SERVICE_KEYS", None):
            context = environment_context(ephemeral=True)
        self.assertEqual(context.public_keys, {context.signer.key_id: context.signer.public_key})
        self.assertTrue(context.signer.key_id.startswith("local-"))

    def test_reopened_service_verifies_and_appends_to_durable_history(self):
        os.environ["SENTILAB_SIGNER_FACTORY"] = "sentilab_core.signing:service_signer"
        with tempfile.TemporaryDirectory() as directory:
            os.environ["SENTILAB_LIVE_DIR"] = directory
            context = environment_context()
            ledger = Ledger(context.root, run_record(), signer=context.signer, public_keys=context.public_keys)
            first = ledger.append("node.create", {"id": "before"}, event_id="before")
            reopened = environment_context()
            ledger = Ledger(reopened.root, run_record(), signer=reopened.signer, public_keys=reopened.public_keys)
            second = ledger.append("node.create", {"id": "after"}, event_id="after")
            state = replay(reopened.root, "test-run", public_keys=reopened.public_keys)
            self.assertIsNone(state["error"])
            self.assertEqual(state["prefix"], [first, second])
            self.assertEqual(second["prev_hash"], first["hash"])


if __name__ == "__main__":
    unittest.main()
