from fastapi import HTTPException, Request

from app.config import get_settings


def get_provided_admin_secret(request: Request) -> str | None:
    header_secret = request.headers.get("X-Admin-Secret")
    if header_secret:
        return header_secret
    return request.query_params.get("secret")


def verify_admin_secret(request: Request) -> None:
    settings = get_settings()
    if not settings.admin_secret:
        raise HTTPException(status_code=404, detail="No encontrado")

    provided = get_provided_admin_secret(request)
    if not provided or provided != settings.admin_secret:
        raise HTTPException(status_code=403, detail="No autorizado")
