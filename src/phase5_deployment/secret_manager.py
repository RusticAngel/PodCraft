"""Google Cloud Secret Manager for runtime API keys.

Secrets are fetched lazily and only when a credentials file or ADC is
available. Keys set directly via env vars (GEMINI_API_KEY,
PARALLEL_API_KEY) always take precedence. Lyria 3 music uses the Gemini
API key.
"""

import os
from typing import Dict, Optional


class SecretManagerClient:
    """Fetch secrets from Google Cloud Secret Manager."""

    def __init__(self, project_id: Optional[str] = None):
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google.cloud import secretmanager

            self._client = secretmanager.SecretManagerServiceClient()
        return self._client

    @property
    def available(self) -> bool:
        if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") and not os.path.exists(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        ):
            return False
        return bool(self.project_id)

    def get_secret(self, secret_name: str, version: str = "latest") -> Optional[str]:
        """Fetch a single secret value, or None on any failure."""
        if not self.available:
            return None
        try:
            client = self._get_client()
            name = f"projects/{self.project_id}/secrets/{secret_name}/versions/{version}"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("utf-8").strip()
        except Exception as e:
            print(f"Secret Manager read failed for '{secret_name}': {e}")
            return None

    def resolve_key(self, env_name: str, secret_name: Optional[str] = None) -> Optional[str]:
        """Resolve a key: env var first, then Secret Manager."""
        direct = os.getenv(env_name)
        if direct:
            return direct
        if secret_name:
            return self.get_secret(secret_name)
        return None

    def env_map(self) -> Dict[str, Optional[str]]:
        """Resolve the full set of runtime keys.

        Lyria 3 music uses the Gemini API key, so no separate Lyria key.
        """
        return {
            "GEMINI_API_KEY": self.resolve_key("GEMINI_API_KEY", "gemini-api-key"),
            "PARALLEL_API_KEY": self.resolve_key("PARALLEL_API_KEY", "parallel-api-key"),
        }