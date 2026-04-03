"""Root test configuration — environment setup before app imports."""

import os

# Must be set before backend.config is imported (which happens at app import time).
# Enables x-enterprise-id header auth instead of requiring real JWTs.
os.environ.setdefault("SPRIH_AUTH_DEV_MODE", "true")
