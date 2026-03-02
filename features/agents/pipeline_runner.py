from __future__ import annotations

import base64
import time

import cv2
import streamlit as st

from config import CAMERA_PROFILE, FRAME_INTERVAL_SECONDS, LIVE_CAMERAS
from features.agents.context_enricher import enrich_context
from features.agents.dispatch_agent import dispatch_incident
from features.agents.escalation_agent import escalate_incident
from features.agents.graph import IncidentState, default_state
from features.agents.record_formatter import format_incident_record
from features.audit.audit_logger import log_incident, next_case_id
from features.detection.vlm_detector import vlm_detect
from features.risk.risk_scorer import score_risk
from features.tracking.tracking_agent import check_tracking_match
def _encode(frame: object) -> str:
    """Return one OpenCV frame as base64 JPEG."""
    ok, buffer = cv2.imencode(".jpg", frame)
    return base64.b64encode(buffer.tobytes()).decode("utf-8") if ok else ""
def _profile(camera_id: str) -> dict[str, object]:
    """Return a camera profile for the selected live camera."""
    camera = next((item for item in LIVE_CAMERAS if item["camera_id"] == camera_id), None)
    return {**CAMERA_PROFILE, "camera_id": camera_id, "location_name": camera["name"] if camera else camera_id}
def _frames(video_path: str):
    """Yield sampled frames from an uploaded camera video."""
    capture = cv2.VideoCapture(video_path)
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 1.0)
    stride = max(int(round(fps * FRAME_INTERVAL_SECONDS)), 1)
    index = count = 0
    try:
        while capture.isOpened():
            ok, frame = capture.read()
            if not ok:
                break
            if index % stride == 0:
                encoded = _encode(frame)
                if encoded:
                    count += 1
                    yield {"frame_b64": encoded, "frame_index": count, "source_offset_seconds": index / fps}
            index += 1
    finally:
        capture.release()
def run_incident_pipeline(state: IncidentState, camera_id: str = "") -> IncidentState:
    """Run the shared incident pipeline for one frame and one camera."""
    current = dict(state)
    current.update(enrich_context(current))
    if camera_id:
        current["camera_profile"] = _profile(camera_id)
    for stage in (vlm_detect, score_risk, escalate_incident):
        current.update(stage(current))
    if current["escalation_mode"] == 3:
        current.update(dispatch_incident({**current, "human_approved": False}))
    current.update(format_incident_record(current))
    return current
def start_camera_pipeline(camera_id: str) -> None:
    """Run Agent 1 continuously for one uploaded camera video."""
    for packet in _frames(str(st.session_state["cameras"][camera_id]["video_path"] or "")):
        cameras = dict(st.session_state["cameras"])
        if not cameras[camera_id]["processing"]:
            break
        state = default_state()
        state.update({"case_id": next_case_id(), "frame_b64": str(packet["frame_b64"]), "frame_index": int(packet["frame_index"]), "source_offset_seconds": float(packet["source_offset_seconds"])})
        result = run_incident_pipeline(state, camera_id)
        if camera_id == LIVE_CAMERAS[1]["camera_id"] and st.session_state["tracking"]["active"]:
            check_tracking_match(
                result["frame_b64"],
                camera_id,
                int(result.get("frame_index", 0)),
                float(result.get("source_offset_seconds", 0.0)),
                bool(result.get("threat_detected", False)),
                str(result.get("frame_description", "")),
            )
        result.update(log_incident(result))
        cameras[camera_id] = {**cameras[camera_id], "current_frame": result["frame_b64"], "incidents": list(cameras[camera_id]["incidents"]) + [result]}
        st.session_state["cameras"] = cameras
        time.sleep(FRAME_INTERVAL_SECONDS)
    cameras = dict(st.session_state["cameras"])
    cameras[camera_id] = {**cameras[camera_id], "processing": False}
    st.session_state["cameras"] = cameras
