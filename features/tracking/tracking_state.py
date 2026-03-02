from __future__ import annotations

from typing_extensions import TypedDict


class TrackingState(TypedDict):
    active: bool
    source_camera_id: str
    search_camera_id: str
    subject_description: str
    user_extra_context: str
    priority: str
    photo_b64: str
    photo_name: str
    sightings: list[dict[str, object]]
    last_sighting: dict[str, object]
    started_at: str
    show_builder: bool
