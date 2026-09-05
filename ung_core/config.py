import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    environment: str = os.getenv("UNG_ENV", "development")
    service_name: str = os.getenv("UNG_SERVICE_NAME", "data-relay")
    database_url: str = os.getenv("DATABASE_URL", "")
    iam_issuer: str = os.getenv("UNG_IAM_ISSUER", "")
    iam_audience: str = os.getenv("UNG_IAM_AUDIENCE", "ung-enterprise")
    sentinel_endpoint: str = os.getenv("UNG_SENTINEL_ENDPOINT", "")
    data_relay_endpoint: str = os.getenv("UNG_DATA_RELAY_ENDPOINT", "")
    require_https: bool = os.getenv("UNG_REQUIRE_HTTPS", "true").lower() == "true"


settings = Settings()
