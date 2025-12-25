import logging

from src.core import emit_start, emit_done, emit_error


logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def main() -> None:
    correlation_id = "test.events.core"

    log.info("Emitting test events for source='test.events'...")

    ev_start_id = emit_start(
        "test.events",
        correlation_id=correlation_id,
        payload={"step": "start", "note": "test start"},
    )

    ev_done_id = emit_done(
        "test.events",
        correlation_id=correlation_id,
        payload={"step": "done", "note": "test done"},
    )

    try:
        raise ValueError("synthetic test error")
    except Exception as exc:  # noqa: BLE001
        ev_err_id = emit_error(
            "test.events",
            correlation_id=correlation_id,
            payload={"step": "error", "error": str(exc)},
        )
    else:
        ev_err_id = 0

    print("Test events emitted:",
          f"start_id={ev_start_id}, done_id={ev_done_id}, error_id={ev_err_id}")


if __name__ == "__main__":
    main()
