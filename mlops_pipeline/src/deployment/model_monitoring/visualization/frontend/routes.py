"""Owner login page for the monitoring visualization service."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates


FRONTEND_DIRECTORY = Path(__file__).parent
templates = Jinja2Templates(directory=str(FRONTEND_DIRECTORY / "templates"))
router = APIRouter(include_in_schema=False)


@router.get("/")
def index(request: Request):
    runtime = getattr(request.app.state, "runtime", None)
    inference_url = (
        runtime.settings.inference_service_url
        if runtime is not None
        else request.app.state.settings.inference_service_url
    )
    return templates.TemplateResponse(
        request,
        "login.html",
        {"inference_service_url": inference_url or ""},
    )
