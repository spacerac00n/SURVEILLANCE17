from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import streamlit as st

from config import (
    CAMERA_PROFILE,
    TIMELINE_WINDOW_SIZE,
    UI_REFRESH_SECONDS,
    VLM_WORKER_COUNT,
    WAITING_ACTION,
    WAITING_SUMMARY,
)
from features.agents.dispatch_agent import dispatch_incident
from features.agents.graph import IncidentState, default_state
from features.agents.pipeline_runner import run_incident_pipeline
from features.agents.record_formatter import format_incident_record
from features.audit.audit_logger import log_incident, next_case_id
from features.dashboard.app import auto_refresh, init_session_state, render_dashboard
from features.ingestion.frame_sampler import sample_frames


def _waiting_state() -> IncidentState:
    """Return a neutral state while the first frame is still processing."""
    state = default_state()
    state["incident_summary"] = WAITING_SUMMARY
    state["recommended_action"] = WAITING_ACTION
    return state


def _fresh_incident(packet: dict[str, object]) -> IncidentState:
    """Create a new incident shell for an incoming frame packet."""
    state = default_state()
    state["case_id"] = next_case_id()
    state["frame_b64"] = str(packet.get("frame_b64", ""))
    state["frame_index"] = int(packet.get("frame_index", 0))
    state["source_offset_seconds"] = float(packet.get("source_offset_seconds", 0.0))
    return state


def _failed_incident(state: IncidentState, exc: Exception) -> IncidentState:
    """Return a fallback incident if a worker crashes."""
    fallback = dict(state)
    stamp = str(fallback.get("timestamp", "")).strip() or datetime.now(
        timezone.utc
    ).isoformat()
    summary = f"Frame {fallback['frame_index']} processing failed."
    fallback.update(
        {
            "camera_profile": dict(fallback.get("camera_profile", {})) or CAMERA_PROFILE,
            "timestamp": stamp,
            "frame_description": "Processing failed before the AI pipeline completed.",
            "incident_summary": summary,
            "recommended_action": "Review this frame manually while the stream continues.",
            "api_error_message": "Pipeline worker failed; fallback response used.",
            "used_fallback": True,
            "detection_status": "fallback",
            "risk_status": "fallback",
            "escalation_status": "fallback",
            "detection_output": {"error": exc.__class__.__name__},
            "risk_output": {"source": "worker_fallback"},
            "escalation_output": {
                "incident_summary": summary,
                "recommended_action": "Review this frame manually while the stream continues.",
            },
            "audit_trail": list(fallback.get("audit_trail", []))
            + [f"Worker failed: {exc.__class__.__name__}"],
        }
    )
    fallback.update(format_incident_record(fallback))
    return fallback


def _session_defaults() -> None:
    """Seed Streamlit session state for the streaming runtime."""
    init_session_state(_waiting_state())
    st.session_state.setdefault("frames", sample_frames())
    st.session_state.setdefault("next_frame_packet", None)
    st.session_state.setdefault("stream_started_at", time.monotonic())
    st.session_state.setdefault(
        "worker_pool",
        ThreadPoolExecutor(max_workers=VLM_WORKER_COUNT),
    )
    st.session_state.setdefault("inflight_jobs", {})
    st.session_state.setdefault("inflight_states", {})
    st.session_state.setdefault("queued_packets", [])
    st.session_state.setdefault("completed_buffer", {})
    st.session_state.setdefault("released_frames", [])
    st.session_state.setdefault("next_release_index", 1)
    st.session_state.setdefault("latest_live_frame_index", 0)
    st.session_state.setdefault("selected_timeline_frame_index", 0)
    st.session_state.setdefault("live_timeline_slider", 0)
    st.session_state.setdefault("stream_ended", False)


def _enqueue_due_packets() -> None:
    """Move source-time-ready packets into the queue."""
    elapsed = time.monotonic() - float(st.session_state["stream_started_at"])
    while not st.session_state["stream_ended"]:
        packet = st.session_state.get("next_frame_packet")
        if packet is None:
            try:
                packet = next(st.session_state["frames"])
            except StopIteration:
                st.session_state["stream_ended"] = True
                break
            st.session_state["next_frame_packet"] = packet
        if float(packet.get("source_offset_seconds", 0.0)) > elapsed:
            break
        st.session_state["queued_packets"].append(packet)
        st.session_state["next_frame_packet"] = None


def _dispatch_queued_packets() -> None:
    """Submit queued frames to the next available worker."""
    while (
        len(st.session_state["inflight_jobs"]) < VLM_WORKER_COUNT
        and st.session_state["queued_packets"]
    ):
        packet = st.session_state["queued_packets"].pop(0)
        state = _fresh_incident(packet)
        frame_index = int(state["frame_index"])
        future = st.session_state["worker_pool"].submit(run_incident_pipeline, state)
        st.session_state["inflight_jobs"][frame_index] = future
        st.session_state["inflight_states"][frame_index] = state


def _collect_finished_jobs() -> None:
    """Move completed worker results into the ordered buffer."""
    finished: list[int] = []
    for frame_index, future in list(st.session_state["inflight_jobs"].items()):
        if not future.done():
            continue
        seed_state = st.session_state["inflight_states"].pop(frame_index)
        try:
            result = future.result()
        except Exception as exc:
            result = _failed_incident(seed_state, exc)
        result.update(log_incident(result))
        st.session_state["completed_buffer"][frame_index] = result
        finished.append(frame_index)
    for frame_index in finished:
        st.session_state["inflight_jobs"].pop(frame_index, None)


def _release_ready_frames() -> None:
    """Release completed frames in strict sequence order."""
    released = st.session_state["released_frames"]
    next_index = int(st.session_state["next_release_index"])
    released_any = False
    while next_index in st.session_state["completed_buffer"]:
        result = st.session_state["completed_buffer"].pop(next_index)
        released.append(result)
        st.session_state["latest_live_frame_index"] = next_index
        st.session_state["incident_state"] = result
        released_any = True
        next_index += 1
    st.session_state["next_release_index"] = next_index
    if len(released) > TIMELINE_WINDOW_SIZE:
        del released[:-TIMELINE_WINDOW_SIZE]
    if released_any:
        latest_index = int(st.session_state.get("latest_live_frame_index", 0))
        st.session_state["selected_timeline_frame_index"] = latest_index
        st.session_state["live_timeline_slider"] = latest_index
    valid_indices = {int(frame["frame_index"]) for frame in released}
    selected = int(st.session_state.get("selected_timeline_frame_index", 0))
    if selected not in valid_indices:
        fallback_index = int(st.session_state.get("latest_live_frame_index", 0))
        st.session_state["selected_timeline_frame_index"] = fallback_index
        st.session_state["live_timeline_slider"] = fallback_index


def _confirm_dispatch(frame_index: int) -> None:
    """Confirm dispatch for a single released frame."""
    released = st.session_state["released_frames"]
    for position, state in enumerate(released):
        if int(state["frame_index"]) != frame_index:
            continue
        if str(state.get("dispatch_status", "")) != "awaiting_confirmation":
            return
        updated = dict(state)
        updated["human_approved"] = True
        updated.update(dispatch_incident(updated))
        updated.update(format_incident_record(updated))
        updated.update(log_incident(updated))
        released[position] = updated
        if frame_index == int(st.session_state.get("latest_live_frame_index", 0)):
            st.session_state["incident_state"] = updated
        return


def _current_live_state() -> IncidentState:
    """Return the latest released frame or a waiting placeholder."""
    latest = int(st.session_state.get("latest_live_frame_index", 0))
    for state in reversed(st.session_state["released_frames"]):
        if int(state["frame_index"]) == latest:
            return state
    return _waiting_state()


def _stream_is_active() -> bool:
    """Return whether the UI should continue polling."""
    return (
        not bool(st.session_state["stream_ended"])
        or bool(st.session_state["queued_packets"])
        or bool(st.session_state["inflight_jobs"])
    )


def main() -> None:
    """Render the Streamlit app and advance the streaming pipeline."""
    _session_defaults()
    _collect_finished_jobs()
    _release_ready_frames()
    _enqueue_due_packets()
    _dispatch_queued_packets()
    live_state = _current_live_state()
    st.session_state["incident_state"] = live_state
    confirmed_frame_index = render_dashboard(
        live_state,
        list(st.session_state["released_frames"]),
    )
    if confirmed_frame_index is not None:
        _confirm_dispatch(confirmed_frame_index)
        st.rerun()
    auto_refresh(_stream_is_active(), UI_REFRESH_SECONDS)


if __name__ == "__main__":
    main()
