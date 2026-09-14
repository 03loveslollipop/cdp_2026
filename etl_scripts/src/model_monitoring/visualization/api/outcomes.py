"""Owner-only observed outcome ingestion."""

from fastapi import APIRouter, HTTPException, Request

from ....database.repositories.outcome_repository import OutcomeConflictError
from ...models.outcomes import OutcomeRequest, OutcomeResponse
from ...services.outcome_service import OutcomeService


router = APIRouter(prefix="/v1", tags=["outcomes"])


@router.post("/outcomes", response_model=OutcomeResponse)
def save_outcomes(payload: OutcomeRequest, request: Request) -> dict:
    runtime = getattr(request.app.state, "runtime", None)
    if runtime is None:
        raise HTTPException(status_code=503, detail="Visualization service is not ready")
    try:
        accepted = OutcomeService(runtime.session_factory).save(payload.outcomes)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except OutcomeConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {"accepted": accepted}
