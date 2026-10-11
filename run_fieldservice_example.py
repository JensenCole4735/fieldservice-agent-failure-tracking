"""Run one field-service agent turn and print its dispatch decision."""

from fieldservice_agent import (
    DemoPhotoAnalyzer,
    InfraiErrors,
    PhotoState,
    WorkOrderPhoto,
    WorkOrderRequest,
    evaluate_work_order,
)


def main() -> None:
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
    decision = evaluate_work_order(order, DemoPhotoAnalyzer(), InfraiErrors())
    print(decision.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
