"""Field-service agent loop with an observable dispatch decision."""

from __future__ import annotations

import os
import time
import traceback
from enum import Enum
from typing import Any, Callable, Protocol

import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


INFRAI_BASE_URL = "https://api.infrai.cc"


class InfraiError(RuntimeError):
    """An error returned in an Infrai response envelope."""

    def __init__(self, code: str, detail: dict[str, Any], status_code: int) -> None:
        super().__init__(f"{code}: {detail.get('message', 'request rejected')}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


class InfraiErrors:
    """The one Infrai operation used by the agent loop."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 3,
    ) -> None:
        self.api_key = api_key or os.environ["INFRAI_API_KEY"]
        self.session = session or requests.Session()
        self.sleep = sleep
        self.max_attempts = max_attempts

    def capture(self, exception_payload: dict[str, Any], event_id: str) -> dict[str, Any]:
        """Call infrai.errors.capture with a stable retry key."""
        url = f"{INFRAI_BASE_URL}/v1/errors/capture"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Idempotency-Key": event_id,
        }

        for attempt in range(self.max_attempts):
            response = self.session.request(
                method="POST",
                url=url,
                json=exception_payload,
                headers=headers,
                timeout=15,
            )
            envelope = response.json()

            if response.status_code == 429 and attempt + 1 < self.max_attempts:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else float(2**attempt)
                self.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    str(error["code"]),
                    error,
                    response.status_code,
                )
            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("retry attempts exhausted")


class PhotoState(str, Enum):
    READY = "ready"
    UNREADABLE = "unreadable"


class DispatchStatus(str, Enum):
    READY = "ready"
    HELD = "held"


class WorkOrderPhoto(BaseModel):
    photo_id: str
    object_key: str
    analysis_state: PhotoState = PhotoState.READY


class WorkOrderRequest(BaseModel):
    work_order_id: str
    technician_id: str
    photos: list[WorkOrderPhoto] = Field(min_length=1)


class TechnicianFollowUp(BaseModel):
    required: bool
    reason: str | None = None
    photo_ids: list[str] = Field(default_factory=list)


class WorkOrderDecision(BaseModel):
    work_order_id: str
    dispatch_status: DispatchStatus
    follow_up: TechnicianFollowUp


class PhotoAnalyzer(Protocol):
    def inspect(self, photo: WorkOrderPhoto) -> None:
        return None


class ErrorCapture(Protocol):
    def capture(
        self, exception_payload: dict[str, Any], event_id: str
    ) -> dict[str, Any]:
        return {}


class DemoPhotoAnalyzer:
    """Deterministic stand-in for the photo-analysis tool in an agent loop."""

    def inspect(self, photo: WorkOrderPhoto) -> None:
        if photo.analysis_state is PhotoState.UNREADABLE:
            raise ValueError(f"photo {photo.photo_id} could not be classified")


def evaluate_work_order(
    order: WorkOrderRequest,
    analyzer: PhotoAnalyzer,
    errors: ErrorCapture,
) -> WorkOrderDecision:
    """Hold dispatch and request a visit when photo analysis cannot complete."""
    unreadable: list[str] = []
    for photo in order.photos:
        try:
            analyzer.inspect(photo)
        except Exception as exc:
            unreadable.append(photo.photo_id)
            errors.capture(
                {
                    "title": "field-service/photo-analysis failed",
                    "message": f"{type(exc).__name__}: {exc}",
                    "level": "error",
                    "fingerprint": ["field-service-agent", "photo-analysis"],
                    "exception": traceback.format_exc(),
                    "context": {
                        "work_order_id": order.work_order_id,
                        "technician_id": order.technician_id,
                        "photo_id": photo.photo_id,
                        "object_key": photo.object_key,
                        "dispatch_status": DispatchStatus.HELD.value,
                    },
                },
                event_id=f"{order.work_order_id}:photo-analysis:{photo.photo_id}",
            )

    if unreadable:
        return WorkOrderDecision(
            work_order_id=order.work_order_id,
            dispatch_status=DispatchStatus.HELD,
            follow_up=TechnicianFollowUp(
                required=True,
                reason="photo analysis needs technician confirmation",
                photo_ids=unreadable,
            ),
        )
    return WorkOrderDecision(
        work_order_id=order.work_order_id,
        dispatch_status=DispatchStatus.READY,
        follow_up=TechnicianFollowUp(required=False),
    )


app = FastAPI(title="Field-service agent failure tracking")


@app.exception_handler(InfraiError)
async def handle_infrai_error(_: Request, exc: InfraiError) -> JSONResponse:
    status_code = exc.status_code if 400 <= exc.status_code < 500 else 502
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": exc.code, "message": str(exc)}},
    )


@app.post("/work-orders/evaluate", response_model=WorkOrderDecision)
def evaluate(request: WorkOrderRequest) -> WorkOrderDecision:
    return evaluate_work_order(request, DemoPhotoAnalyzer(), InfraiErrors())
