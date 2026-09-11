"""Server-rendered frontend entry point."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates


templates = Jinja2Templates(directory=str(Path(__file__).with_name("templates")))
router = APIRouter(include_in_schema=False)


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {})
