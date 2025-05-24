from sqlmodel import Session, select
from typing import List

from .models import ExperimentTelemetryEvent, ExperimentTelemetryEventCreate

def create_telemetry_event(session: Session, event_data: ExperimentTelemetryEventCreate) -> ExperimentTelemetryEvent:
    """
    Creates a new telemetry event in the database.
    """
    db_event = ExperimentTelemetryEvent.from_orm(event_data)
    session.add(db_event)
    session.commit()
    session.refresh(db_event)
    return db_event

def get_telemetry_events_by_session(session: Session, session_id: str, limit: int = 1000) -> List[ExperimentTelemetryEvent]:
    """
    Retrieves all telemetry events for a given session_id, ordered by timestamp.
    Includes a limit to prevent overly large responses.
    """
    statement = select(ExperimentTelemetryEvent).where(ExperimentTelemetryEvent.session_id == session_id).order_by(ExperimentTelemetryEvent.timestamp).limit(limit)
    results = session.exec(statement)
    events = results.all()
    return events
