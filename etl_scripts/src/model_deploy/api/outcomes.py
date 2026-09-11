"""Observed outcome ingestion endpoint."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from ...database.repositories.outcome_repository import OutcomeConflictError
from ..dependencies import Runtime, get_runtime
from ..models import OutcomeRequest, OutcomeResponse
from ..services.outcome_service import OutcomeService


router = APIRouter(prefix="/v1", tags=["outcomes"])


@router.post("/outcomes", response_model=OutcomeResponse)
def save_outcomes(
    payload: OutcomeRequest,
    runtime: Annotated[Runtime, Depends(get_runtime)],
) -> dict:
    try:
        accepted = OutcomeService(runtime.session_factory).save(payload.outcomes)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except OutcomeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"accepted": accepted}
