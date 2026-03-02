from __future__ import annotations

import threading

import streamlit as st
from streamlit.runtime.scriptrunner import add_script_run_ctx, get_script_run_ctx

from config import COLOR_CRITERIA
from features.agents.graph import IncidentState
from features.agents.record_formatter import build_ai_incident_record
from features.tracking.tracking_agent import start_tracking
from features.tracking.tracking_state import TrackingState


def _humanize(text: str) -> str:
    """Convert machine labels into readable text."""
    return text.replace("_", " ").strip() or "unknown"


def _record_for_state(state: IncidentState) -> dict[str, object]:
    """Return the cached incident record or build one on demand."""
    record = dict(state.get("ai_incident_record", {}))
    return record or build_ai_incident_record(state)


def build_color_reason(record: dict[str, object]) -> str:
    """Explain the displayed color from deterministic state data."""
    status = dict(record.get("status", {}))
    details = dict(record.get("key_details", {}))
    color = str(status.get("threat_color", "green"))
    color = color if color in COLOR_CRITERIA else "green"
    label = str(status.get("threat_label", COLOR_CRITERIA[color]["label"]))
    mode = int(status.get("escalation_mode", 1))
    score = float(details.get("risk_score", 0.0))
    band_min, band_max = COLOR_CRITERIA[color]["risk_range"]
    reason = (
        f"The frame is marked {label} ({color.title()}) because the risk score of "
        f"{score:.1f} falls within the {band_min:.1f}-{band_max:.1f} {label} band. "
    )
    if color == "green":
        if bool(details.get("threat_detected", False)):
            threat = _humanize(str(details.get("threat_type", "none")))
            confidence = str(details.get("confidence", "low")).lower()
            return (
                reason
                + f"The system noted {threat} at {confidence} confidence, but no "
                f"elevated indicators were strong enough to move the frame beyond "
                f"routine monitoring at escalation mode {mode}."
            )
        return (
            reason
            + f"No immediate threat was detected, so the system kept this frame in "
            f"routine monitoring at escalation mode {mode}."
        )
    threat = _humanize(str(details.get("threat_type", "none")))
    confidence = str(details.get("confidence", "low")).lower()
    if not bool(details.get("threat_detected", False)) or threat == "none":
        return (
            reason
            + f"The system detected elevated risk cues, which still maps this "
            f"incident to escalation mode {mode}."
        )
    return (
        reason
        + f"The system flagged {threat} with {confidence} confidence, which maps "
        f"this incident to escalation mode {mode}."
    )


def render_decision_reasoning(record: dict[str, object]) -> None:
    """Render the existing decision path as a readable sequence."""
    stages = list(record.get("decision_path", []))
    if not stages:
        st.caption("No decision reasoning recorded yet.")
        return
    for index, stage in enumerate(stages, start=1):
        stage_data = dict(stage)
        status = _humanize(str(stage_data.get("status", "completed"))).title()
        st.markdown(f"**{index}. {stage_data.get('stage_name', 'Stage')}**")
        st.caption(f"Status: {status}")
        st.write(str(stage_data.get("summary", "")))


def _start_tracking(state: IncidentState) -> None:
    """Seed tracking state and launch Agent 2 in a background thread."""
    tracking = {
        **dict(st.session_state["tracking"]),
        "active": True,
        "camera_id": str(state.get("camera_profile", {}).get("camera_id", "")),
        "subject_description": str(state.get("frame_description", "")),
        "observations": [],
        "consecutive_lost_count": 0,
        "subject_lost": False,
        "subject_lost_timestamp": "",
        "bolo_active": False,
        "bolo_text": "",
        "reacquired": False,
        "reacquired_camera_id": "",
        "reacquired_frame_path": None,
        "reacquired_timestamp": "",
        "reacquired_confidence": "",
    }
    st.session_state["tracking"] = tracking
    thread = threading.Thread(
        target=start_tracking,
        args=(TrackingState(**dict(tracking)),),
        daemon=True,
    )
    add_script_run_ctx(thread, get_script_run_ctx())
    thread.start()


def _render_tracking_controls(state: IncidentState, key_suffix: str) -> None:
    """Render the track button and operator context input."""
    tracking = dict(st.session_state["tracking"])
    input_key = "tracking_context_input" if key_suffix == "active" else f"tracking_context_{key_suffix}"
    if input_key not in st.session_state:
        st.session_state[input_key] = str(tracking.get("user_extra_context", ""))
    action_col, input_col = st.columns((1, 2))
    with action_col:
        disabled = bool(tracking.get("active")) or bool(tracking.get("bolo_active"))
        label = "TRACKING ACTIVE" if disabled else "Track"
        if st.button(label, key=f"track_person_{key_suffix}", disabled=disabled):
            _start_tracking(state)
            st.rerun()
    with input_col:
        value = st.text_input(
            "Add context for tracking agent (optional)",
            key=input_key,
            placeholder="e.g. suspect heading toward exit B",
        )
    st.session_state["tracking"] = {**dict(st.session_state["tracking"]), "user_extra_context": value}


def render_report_card(
    state: IncidentState,
    show_confirm: bool,
    key_suffix: str = "default",
) -> bool:
    """Render the operator-facing report card and return confirm state."""
    record = _record_for_state(state)
    status = dict(record.get("status", {}))
    details = dict(record.get("key_details", {}))
    color = str(status.get("threat_color", "green"))
    color = color if color in COLOR_CRITERIA else "green"
    label = str(status.get("threat_label", COLOR_CRITERIA[color]["label"]))
    summary = str(state.get("incident_summary", "")).strip() or str(
        record.get("executive_summary", "")
    ).strip()
    if bool(details.get("threat_detected", False)):
        threat = _humanize(str(details.get("threat_type", "none"))).title()
        confidence = str(details.get("confidence", "low")).lower()
        observed = f"Observed threat: {threat} ({confidence} confidence)."
    else:
        observed = "Observed threat: No immediate threat detected."
    try:
        container = st.container(border=True)
    except TypeError:
        container = st.container()
    with container:
        st.subheader("Report Card")
        st.caption(
            " | ".join(
                [
                    f"Frame #{int(state.get('frame_index', 0))}",
                    f"Source Time: {float(state.get('source_offset_seconds', 0.0)):.1f}s",
                ]
            )
        )
        confirmed = False
        score_col, badge_col = st.columns(2)
        score_col.metric("Risk Score", f"{float(details.get('risk_score', 0.0)):.1f}")
        with badge_col:
            if show_confirm and str(status.get("dispatch_status", "")) == "awaiting_confirmation":
                confirmed = st.button(
                    "Confirm Dispatch",
                    type="primary",
                    key=f"confirm_dispatch_{int(state.get('frame_index', 0))}_{key_suffix}",
                )
            st.caption("Threat Level")
            st.markdown(
                f"<div style='padding:0.75rem;background:{COLOR_CRITERIA[color]['hex']};"
                f"color:white;font-weight:700;border-radius:0.5rem;text-align:center;'>"
                f"{label} ({color.title()})</div>",
                unsafe_allow_html=True,
            )
        st.markdown("**What Is Happening**")
        st.write(summary or "No incident summary available.")
        st.caption(observed)
        with st.expander("Why This Color", expanded=False):
            st.write(build_color_reason(record))
        with st.expander("Other Data", expanded=False):
            st.markdown("**Timestamp**")
            st.write(str(record.get("timestamp", "")) or "Not available.")
            st.markdown("**Decision Reasoning Path**")
            render_decision_reasoning(record)
        _render_tracking_controls(state, key_suffix)
    return confirmed if show_confirm else False
