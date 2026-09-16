"""JSON and CSV prediction endpoints."""

from __future__ import annotations

import io
import json
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile

from ..dependencies import Runtime, get_runtime
from ..models import PredictionRequest, PredictionResponse
from ..services.prediction_service import (
    IdempotencyConflictError,
    PredictionService,
    PredictionValidationError,
)


router = APIRouter(prefix="/v1/predictions", tags=["predictions"])
IdempotencyKey = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=8, max_length=128),
]


def _service(runtime: Runtime, request: Request) -> PredictionService:
    principal = getattr(request.state, "principal", None)
    return PredictionService(
        runtime.artifact,
        runtime.model_version_id,
        runtime.session_factory,
        runtime.settings.max_batch_rows,
        requested_by_user_id=getattr(principal, "user_id", None),
    )


def _predict(service: PredictionService, records: list[dict], key: str) -> dict:
    try:
        return service.predict(records, key)
    except PredictionValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except IdempotencyConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("", response_model=PredictionResponse)
def predict_json(
    payload: PredictionRequest,
    request: Request,
    idempotency_key: IdempotencyKey,
    runtime: Annotated[Runtime, Depends(get_runtime)],
) -> dict:
    return _predict(_service(runtime, request), payload.records, idempotency_key)


@router.post("/csv", response_model=PredictionResponse)
def predict_csv(
    request: Request,
    idempotency_key: IdempotencyKey,
    runtime: Annotated[Runtime, Depends(get_runtime)],
    file: UploadFile = File(...),
) -> dict:
    content = file.file.read(runtime.settings.max_upload_bytes + 1)
    if len(content) > runtime.settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="CSV upload exceeds configured limit")
    try:
        frame = pd.read_csv(io.BytesIO(content))
    except (pd.errors.ParserError, UnicodeDecodeError, ValueError) as error:
        raise HTTPException(status_code=422, detail=f"Invalid CSV: {error}") from error
    if frame.columns.duplicated().any():
        raise HTTPException(status_code=422, detail="CSV contains duplicate columns")
    records = json.loads(frame.to_json(orient="records", date_format="iso"))
    return _predict(_service(runtime, request), records, idempotency_key)
