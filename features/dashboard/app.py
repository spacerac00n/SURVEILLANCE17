from __future__ import annotations

import base64
import html
import threading
import time
from copy import deepcopy
from pathlib import Path

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from config import DATA_DIR, LIVE_CAMERAS
from features.agents.dispatch_agent import dispatch_incident
from features.agents.graph import IncidentState
from features.agents.pipeline_runner import start_camera_pipeline
from features.agents.record_formatter import build_ai_incident_record, format_incident_record
from features.audit.audit_logger import get_audit_by_camera, log_incident
from features.dashboard.report_card import render_report_card
from features.tracking.camera_map import render_camera_map
from features.tracking.tracking_state import TrackingState


def _tracking_state() -> TrackingState:
    """Return the default tracking state."""
    return TrackingState(active=False, camera_id="", subject_description="", user_extra_context="", observations=[], consecutive_lost_count=0, subject_lost=False, subject_lost_timestamp="", bolo_active=False, bolo_text="", reacquired=False, reacquired_camera_id="", reacquired_frame_path=None, reacquired_timestamp="", reacquired_confidence="")


def init_session_state(default_state: IncidentState) -> None:
    """Seed Streamlit session state for the multi-camera dashboard."""
    st.session_state.setdefault("incident_state", deepcopy(default_state))
    st.session_state.setdefault("active_camera", None)
    st.session_state.setdefault("tracking", _tracking_state())
    st.session_state.setdefault("cameras", {cam["camera_id"]: {"video_path": None, "processing": False, "incidents": [], "current_frame": None, "upload_token": ""} for cam in LIVE_CAMERAS})


def _frame_bytes(frame_b64: str) -> bytes | None:
    """Decode a base64 frame for display."""
    try:
        return base64.b64decode(frame_b64) if frame_b64 else None
    except Exception:
        return None


def _save_upload(upload: object, camera_id: str) -> tuple[str, str]:
    """Persist one uploaded video to disk and return its path and token."""
    path = Path(DATA_DIR) / f"{camera_id}.mp4"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(upload.getvalue())
    return str(path), f"{upload.name}:{upload.size}"


def _start_camera(camera_id: str) -> None:
    """Launch one Agent 1 thread for a live camera."""
    thread = threading.Thread(target=start_camera_pipeline, args=(camera_id,), daemon=True)
    add_script_run_ctx(thread, get_script_run_ctx())
    thread.start()


def _confirm_camera_incident(camera_id: str, case_id: str) -> None:
    """Finalise dispatch approval for one per-camera incident."""
    cameras = dict(st.session_state["cameras"])
    incidents = list(cameras[camera_id]["incidents"])
    for index, incident in enumerate(incidents):
        if str(incident.get("case_id")) != case_id or str(incident.get("dispatch_status")) != "awaiting_confirmation":
            continue
        updated = {**incident, "human_approved": True}
        updated.update(dispatch_incident(updated))
        updated.update(format_incident_record(updated))
        updated.update(log_incident(updated))
        incidents[index] = updated
        cameras[camera_id] = {**cameras[camera_id], "incidents": incidents}
        st.session_state["cameras"] = cameras
        return


def _render_bolo_card() -> None:
    """Render the global BOLO card and any re-acquisition details."""
    tracking = dict(st.session_state["tracking"])
    if not tracking["bolo_active"]:
        return
    st.markdown("<div style='background:#2c0a0a;color:white;padding:20px;border-radius:14px;'><div style='color:#e74c3c;font-weight:700;'>⚠ BOLO ISSUED — " + html.escape(str(tracking["subject_lost_timestamp"])) + "</div><pre style='margin:12px 0 0;white-space:pre-wrap;font-family:monospace;color:white;'>" + html.escape(str(tracking["bolo_text"])) + ("</pre><hr style='border:0;border-top:2px solid #2ecc71;'><div style='color:#2ecc71;font-weight:700;'>✅ SUBJECT RE-ACQUIRED — " + html.escape(str(tracking["reacquired_timestamp"])) + "</div><div>Camera: " + html.escape(str(tracking["reacquired_camera_id"])) + "</div><div>Confidence: " + html.escape(str(tracking["reacquired_confidence"])) + "</div>" if tracking["reacquired"] else "</pre>") + "</div>", unsafe_allow_html=True)
    if tracking["reacquired_frame_path"]:
        st.image(str(tracking["reacquired_frame_path"]), width=200)


def _render_incident(incident: dict[str, object], key_suffix: str) -> None:
    """Render one incident report card and handle confirmation."""
    if render_report_card(incident, True, key_suffix):
        _confirm_camera_incident(str(incident.get("camera_profile", {}).get("camera_id", "")), str(incident.get("case_id", "")))
        st.rerun()


def _render_waiting_state() -> None:
    """Render a neutral waiting state before any released frames exist."""
    st.info("Waiting for first processed frame.")


def _timeline_frame(released_frames: list[IncidentState]) -> IncidentState | None:
    """Return the currently selected released frame."""
    if not released_frames:
        return None
    options = [int(frame.get("frame_index", 0)) for frame in released_frames]
    latest = options[-1]
    selected = int(st.session_state.get("selected_timeline_frame_index", latest))
    if selected not in options:
        selected = latest
        st.session_state["selected_timeline_frame_index"] = selected
        st.session_state["live_timeline_slider"] = selected
    if len(options) == 1:
        st.caption(f"Frame Timeline: Frame {options[0]}")
    else:
        if st.session_state.get("live_timeline_slider") not in options:
            st.session_state["live_timeline_slider"] = selected
        selected = int(
            st.select_slider(
                "Frame Timeline",
                options=options,
                key="live_timeline_slider",
                format_func=lambda value: f"Frame {value}",
            )
        )
        st.session_state["selected_timeline_frame_index"] = selected
    for frame in released_frames:
        if int(frame.get("frame_index", 0)) == selected:
            return frame
    return released_frames[-1]


def _history_rows(released_frames: list[IncidentState]) -> list[dict[str, object]]:
    """Return compact rows for the history table."""
    rows: list[dict[str, object]] = []
    for frame in reversed(released_frames):
        rows.append(
            {
                "Frame": int(frame.get("frame_index", 0)),
                "Case ID": str(frame.get("case_id", "")),
                "Threat": str(frame.get("threat_label", "")).strip() or str(frame.get("threat_color", "")).title(),
                "Dispatch": str(frame.get("dispatch_status", "")),
                "Time": str(frame.get("timestamp", "")),
            }
        )
    return rows


def _render_global_view(
    _live_state: IncidentState,
    released_frames: list[IncidentState],
) -> int | None:
    """Render the original main dashboard under the camera map."""
    render_camera_map()
    _render_bolo_card()
    live_tab, history_tab = st.tabs(["Live Incident", "Incident History"])
    with live_tab:
        if not released_frames:
            _render_waiting_state()
        else:
            selected = _timeline_frame(released_frames)
            if selected is not None:
                selected_bytes = _frame_bytes(str(selected.get("frame_b64", "")))
                if selected_bytes:
                    st.image(selected_bytes, width="stretch")
                if render_report_card(selected, True, "global_live"):
                    return int(selected.get("frame_index", 0))
    with history_tab:
        if not released_frames:
            st.info("No incidents recorded yet.")
        else:
            with st.expander("Incident History Table", expanded=False):
                st.dataframe(_history_rows(released_frames), width="stretch")
            for frame in reversed(released_frames):
                label = f"Frame {int(frame.get('frame_index', 0))} — {frame.get('case_id', '')}"
                with st.expander(label, expanded=False):
                    if render_report_card(frame, True, f"global_history_{int(frame.get('frame_index', 0))}"):
                        return int(frame.get("frame_index", 0))
    return None


def _render_camera_view(camera_id: str) -> None:
    """Render one full single-camera dashboard."""
    cameras = dict(st.session_state["cameras"])
    camera = dict(cameras[camera_id])
    if st.button("← All Cameras", key=f"back_{camera_id}"):
        st.session_state["active_camera"] = None
        st.rerun()
    st.title(next((cam["name"] for cam in LIVE_CAMERAS if cam["camera_id"] == camera_id), camera_id))
    if st.session_state["tracking"]["active"] and st.session_state["tracking"]["camera_id"] == camera_id:
        st.info("TRACKING ACTIVE")
    upload = None if camera["video_path"] else st.file_uploader(f"Upload video for {camera_id}", type=["mp4", "mov"], key=f"upload_{camera_id}") if (camera_id != LIVE_CAMERAS[1]["camera_id"] or st.session_state["tracking"]["bolo_active"]) else None
    if camera_id == LIVE_CAMERAS[1]["camera_id"] and not camera["video_path"] and not st.session_state["tracking"]["bolo_active"]:
        st.info("Waiting for BOLO before Camera 2 can be activated")
    if upload:
        path, token = _save_upload(upload, camera_id)
        if token != camera.get("upload_token"):
            cameras[camera_id] = {"video_path": path, "processing": True, "incidents": [], "current_frame": None, "upload_token": token}
            st.session_state["cameras"] = cameras
            _start_camera(camera_id)
            st.rerun()
    if camera.get("current_frame"):
        st.image(_frame_bytes(str(camera["current_frame"])), width="stretch")
    incidents = list(camera.get("incidents", []))
    if incidents:
        st.markdown("**Active Incident**")
        _render_incident(incidents[-1], "active")
    history = list(reversed(incidents[:-1])) if len(incidents) > 1 else []
    if history:
        st.markdown("**Incident History**")
        for index, incident in enumerate(history, start=1):
            with st.expander(f"Incident {index} — {incident.get('case_id', '')}", expanded=False):
                _render_incident(incident, f"history_{camera_id}_{index}")
    elif not incidents:
        for incident in reversed(get_audit_by_camera(camera_id)):
            with st.expander(f"Audit — {incident.get('case_id', '')}", expanded=False):
                _render_incident(incident, f"audit_{camera_id}_{incident.get('case_id', '')}")


def render_dashboard(live_state: IncidentState, released_frames: list[IncidentState]) -> int | None:
    """Render the global view or one single-camera view."""
    if st.session_state["active_camera"] is None:
        return _render_global_view(live_state, released_frames)
    _render_camera_view(str(st.session_state["active_camera"]))
    return None


def auto_refresh(active: bool, interval_seconds: float) -> None:
    """Refresh while any camera pipeline or tracking flow is active."""
    cameras = dict(st.session_state.get("cameras", {}))
    processing = any(bool(camera.get("processing")) for camera in cameras.values())
    tracking = dict(st.session_state.get("tracking", {}))
    if not active and not processing and not tracking.get("active") and not tracking.get("bolo_active"):
        return
    time.sleep(interval_seconds if active or processing else 3.0)
    st.rerun()
