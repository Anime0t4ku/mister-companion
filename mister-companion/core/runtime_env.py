import os
from pathlib import Path

from core.app_paths import is_macos_packaged_app


def configure_packaged_certificates():
    if not is_macos_packaged_app():
        return

    try:
        import certifi
    except Exception:
        return

    cert_path = certifi.where()
    if not cert_path or not Path(cert_path).is_file():
        return

    os.environ.setdefault("SSL_CERT_FILE", cert_path)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", cert_path)
