from typing import Any

from fieldservice_agent import (
    DemoPhotoAnalyzer,
    DispatchStatus,
    PhotoState,
    WorkOrderPhoto,
    WorkOrderRequest,
    evaluate_work_order,
)


class RecordingErrors:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], str]] = []

    def capture(self, exception_payload: dict[str, Any], event_id: str) -> dict[str, Any]:
        self.calls.append((exception_payload, event_id))
        return {"event_id": "evt-1"}


def test_unreadable_photo_holds_dispatch_and_schedules_follow_up() -> None:
    errors = RecordingErrors()
    order = WorkOrderRequest(
        work_order_id="WO-1042",
        technician_id="TECH-17",
        photos=[
            WorkOrderPhoto(
                photo_id="PHOTO-2",
                object_key="work-orders/WO-1042/arrival.jpg",
                analysis_state=PhotoState.UNREADABLE,
            )
        ],
    )

    decision = evaluate_work_order(order, DemoPhotoAnalyzer(), errors)

    assert decision.dispatch_status is DispatchStatus.HELD
    assert decision.follow_up.required is True
    assert decision.follow_up.photo_ids == ["PHOTO-2"]
    assert len(errors.calls) == 1
    payload, event_id = errors.calls[0]
    assert payload["fingerprint"] == ["field-service-agent", "photo-analysis"]
    assert payload["context"]["dispatch_status"] == "held"
    assert event_id == "WO-1042:photo-analysis:PHOTO-2"
