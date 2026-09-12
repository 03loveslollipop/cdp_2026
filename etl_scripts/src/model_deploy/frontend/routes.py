"""Server-rendered frontend entry point."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates


FRONTEND_DIRECTORY = Path(__file__).parent
templates = Jinja2Templates(directory=str(FRONTEND_DIRECTORY / "templates"))
router = APIRouter(include_in_schema=False)


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"monitor_ui_url": request.app.state.settings.monitor_ui_url or ""},
    )


@router.get("/inference/")
def inference(request: Request):
    return templates.TemplateResponse(
        request,
        "inference.html",
        {"monitor_ui_url": request.app.state.settings.monitor_ui_url or ""},
    )
