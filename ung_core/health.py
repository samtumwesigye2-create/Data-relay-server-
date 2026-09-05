from .config import settings
from .contracts import ServiceHealth


def get_health() -> ServiceHealth:
    details = {
        "environment": settings.environment,
        "database_configured": bool(settings.database_url),
        "iam_configured": bool(settings.iam_issuer),
        "sentinel_configured": bool(settings.sentinel_endpoint),
    }
    status = "ok" if details["database_configured"] and details["iam_configured"] else "degraded"
    return ServiceHealth(service=settings.service_name, status=status, details=details)
