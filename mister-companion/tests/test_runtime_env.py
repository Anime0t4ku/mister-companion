import os
import sys
import unittest
from unittest.mock import patch

import certifi

from core.runtime_env import configure_packaged_certificates


class ConfigurePackagedCertificatesTest(unittest.TestCase):
    def test_sets_certifi_env_for_packaged_macos_app(self):
        with (
            patch.object(sys, "platform", "darwin"),
            patch.object(sys, "frozen", True, create=True),
            patch.dict(os.environ, {}, clear=True),
        ):
            configure_packaged_certificates()

            self.assertEqual(os.environ["SSL_CERT_FILE"], certifi.where())
            self.assertEqual(os.environ["REQUESTS_CA_BUNDLE"], certifi.where())

    def test_does_not_overwrite_existing_cert_env(self):
        env = {
            "SSL_CERT_FILE": "/custom/ssl.pem",
            "REQUESTS_CA_BUNDLE": "/custom/requests.pem",
        }
        with (
            patch.object(sys, "platform", "darwin"),
            patch.object(sys, "frozen", True, create=True),
            patch.dict(os.environ, env, clear=True),
        ):
            configure_packaged_certificates()

            self.assertEqual(os.environ["SSL_CERT_FILE"], "/custom/ssl.pem")
            self.assertEqual(os.environ["REQUESTS_CA_BUNDLE"], "/custom/requests.pem")

    def test_does_nothing_outside_packaged_macos_app(self):
        with (
            patch.object(sys, "platform", "linux"),
            patch.object(sys, "frozen", True, create=True),
            patch.dict(os.environ, {}, clear=True),
        ):
            configure_packaged_certificates()

            self.assertNotIn("SSL_CERT_FILE", os.environ)
            self.assertNotIn("REQUESTS_CA_BUNDLE", os.environ)


if __name__ == "__main__":
    unittest.main()
