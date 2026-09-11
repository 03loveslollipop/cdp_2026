"""Active model metadata endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends

from ..dependencies import Runtime, get_runtime
from ..models import ModelResponse


router = APIRouter(prefix="/v1", tags=["model"])


@router.get("/model", response_model=ModelResponse)
def model_metadata(runtime: Annotated[Runtime, Depends(get_runtime)]) -> dict:
    manifest = runtime.artifact.manifest
    return {
        "model_version_id": runtime.model_version_id,
        "model_family": manifest["model_family"],
        "artifact_sha256": manifest["artifact_sha256"],
        "threshold": manifest["threshold"],
        "class_order": manifest["class_order"],
        "stage": manifest["stage"],
        "source_revision": manifest.get("source_revision"),
        "required_predictors": manifest["required_predictors"],
    }
