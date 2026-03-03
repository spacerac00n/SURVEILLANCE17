from __future__ import annotations

import html
from datetime import datetime, timezone

import streamlit as st

from config import COLOR_CRITERIA, LIVE_CAMERAS
from features.agents.graph import IncidentState
from features.agents.record_formatter import build_ai_incident_record
from features.tracking.tracking_agent import start_tracking
from features.tracking.tracking_state import TrackingState


def _humanize(text: str) -> str:
    """Convert machine labels into readable text."""
    return text.replace("_", " ").strip() or "unknown"


def _confidence_display(value: object) -> str:
    """Return a readable confidence score for the report card."""
    text = str(value).strip().lower()
    mapping = {
        "low": "25%",
        "medium": "50%",
        "high": "75%",
        "very high": "90%",
        "very_high": "90%",
        "certain": "90%",
    }
    if text in mapping:
        return mapping[text]
    if text.endswith("%"):
        return text
    try:
        numeric = float(text)
    except ValueError:
        return "25%"
    if numeric <= 1:
        numeric *= 100
    return f"{int(round(numeric))}%"


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


def _source_camera_id(state: IncidentState) -> str:
    """Map the demo's default stream to Camera 1 for tracking."""
    camera_id = str(state.get("camera_profile", {}).get("camera_id", ""))
    live_ids = {camera["camera_id"] for camera in LIVE_CAMERAS}
    return camera_id if camera_id in live_ids else LIVE_CAMERAS[0]["camera_id"]


def _priority_from_state(state: IncidentState) -> str:
    """Map the incident color into the Track Card priority scale."""
    color = str(state.get("threat_color", "")).strip().lower()
    if color in {"red", "orange"}:
        return "red"
    if color == "yellow":
        return "yellow"
    return "green"


def _start_tracking(state: IncidentState) -> None:
    """Seed the Track Card state for the hackathon demo."""
    tracking: TrackingState = {
        "active": True,
        "source_camera_id": _source_camera_id(state),
        "search_camera_id": LIVE_CAMERAS[1]["camera_id"],
        "subject_description": str(state.get("frame_description", "")),
        "threat_type": _humanize(str(state.get("threat_type", "unknown"))).title(),
        "user_extra_context": str(st.session_state["tracking"].get("user_extra_context", "")),
        "priority": _priority_from_state(state),
        "photo_b64": "",
        "photo_name": "",
        "sightings": [],
        "last_sighting": {},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "show_builder": False,
    }
    start_tracking(tracking)


def _render_tracking_controls(state: IncidentState, key_suffix: str) -> None:
    """Render the track button first, then the context input after activation."""
    if _source_camera_id(state) != LIVE_CAMERAS[0]["camera_id"]:
        return
    tracking = dict(st.session_state["tracking"])
    is_active = bool(tracking.get("active"))
    button_label = "TRACKING ACTIVE" if is_active else "Track"
    if st.button(
        button_label,
        key=f"track_person_{key_suffix}",
        disabled=is_active,
        use_container_width=True,
    ):
        _start_tracking(state)
        st.rerun()
    if not is_active:
        return
    input_key = (
        "tracking_context_input"
        if key_suffix == "active"
        else f"tracking_context_{key_suffix}"
    )
    if input_key not in st.session_state:
        st.session_state[input_key] = str(tracking.get("user_extra_context", ""))
    value = st.text_input(
        "Add context for tracking agent (optional)",
        key=input_key,
        placeholder="e.g. suspect heading toward exit B",
    )
    st.session_state["tracking"] = {
        **dict(st.session_state["tracking"]),
        "user_extra_context": value,
    }


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
    summary = str(state.get("incident_summary", "")).strip() or str(
        record.get("executive_summary", "")
    ).strip()
    if bool(details.get("threat_detected", False)):
        threat = _humanize(str(details.get("threat_type", "none"))).title()
        confidence = str(details.get("confidence", "low")).lower()
        observed = f"Observed threat: {threat} ({confidence} confidence)."
    else:
        observed = "Observed threat: No immediate threat detected."
    badge_styles = {
        "green": {"label": "Low Risk", "color": "#22c55e"},
        "yellow": {"label": "Medium", "color": "#eab308"},
        "orange": {"label": "High", "color": "#f97316"},
        "red": {"label": "Critical", "color": "#ef4444"},
    }
    badge_style = badge_styles.get(color, badge_styles["green"])
    tracking = dict(st.session_state.get("tracking", {}))
    track_status = "Active" if bool(tracking.get("active")) else "Ready"
    confidence_label = _humanize(str(details.get("confidence", "low"))).title()
    confidence_score = _confidence_display(details.get("confidence", "low"))
    source_name = "Camera 1" if _source_camera_id(state) == LIVE_CAMERAS[0]["camera_id"] else _source_camera_id(state)
    frame_meta = (
        f"Frame #{int(state.get('frame_index', 0))} | "
        f"Source Time: {float(state.get('source_offset_seconds', 0.0)):.1f}s"
    )
    container = st.container()
    with container:
        st.markdown(
            "<div style='font-size:1.15rem;font-weight:700;line-height:1.2;margin-bottom:0.75rem;'>"
            "Report Card"
            "</div>",
            unsafe_allow_html=True,
        )
        confirmed = False
        top_left, top_right = st.columns((1.1, 1), gap="medium")
        with top_left:
            st.markdown(
                "<div style='background:#0f172a;border:1px solid rgba(255,255,255,0.08);"
                "border-radius:16px;padding:1rem 1rem 0.95rem;'>"
                "<div style='color:rgba(255,255,255,0.72);font-size:0.88rem;font-weight:700;"
                "line-height:1.2;margin-bottom:0.35rem;'>Risk Score</div>"
                f"<div style='color:#ffffff;font-size:3.1rem;font-weight:800;line-height:1.02;'>"
                f"{float(details.get('risk_score', 0.0)):.1f}</div>"
                f"<div style='margin-top:0.85rem;'><span style='display:inline-block;"
                f"padding:0.48rem 0.9rem;border-radius:999px;background:{badge_style['color']};"
                "color:#ffffff;font-size:0.92rem;font-weight:700;line-height:1;'>"
                f"{badge_style['label']}</span></div>"
                "</div>",
                unsafe_allow_html=True,
            )
        with top_right:
            st.markdown(
                "<div style='background:#0f172a;border:1px solid rgba(255,255,255,0.08);"
                "border-radius:16px;padding:1rem;color:#ffffff;font-size:0.98rem;"
                "font-weight:600;line-height:1.45;'>"
                f"Track: {html.escape(track_status)}<br>"
                f"Confidence: {html.escape(confidence_score)} ({html.escape(confidence_label)})"
                "</div>"
                "<div style='background:#0f172a;border:1px solid rgba(255,255,255,0.08);"
                "border-top:0;border-radius:0 0 16px 16px;padding:0 1rem 1rem;color:rgba(255,255,255,0.64);"
                "font-size:0.84rem;line-height:1.4;"
                "margin-top:0.15rem;'>"
                f"{html.escape(source_name)} | {html.escape(frame_meta)}"
                "</div>",
                unsafe_allow_html=True,
            )
            st.markdown("<div style='height:0.7rem;'></div>", unsafe_allow_html=True)
            action_col, track_col = st.columns((1.05, 1), gap="small")
            with action_col:
                if show_confirm and str(status.get("dispatch_status", "")) == "awaiting_confirmation":
                    confirmed = st.button(
                        "Confirm Dispatch",
                        type="primary",
                        key=f"confirm_dispatch_{int(state.get('frame_index', 0))}_{key_suffix}",
                        use_container_width=True,
                    )
                else:
                    st.markdown(
                        "<div style='height:2.5rem;'></div>",
                        unsafe_allow_html=True,
                    )
            with track_col:
                _render_tracking_controls(state, key_suffix)
        st.markdown(
            "<div style='background:#0f172a;border:1px solid rgba(255,255,255,0.08);"
            "border-radius:16px;padding:1rem 1rem 0.9rem;margin-top:0.85rem;'>"
            "<div style='color:#ffffff;font-size:1rem;font-weight:700;line-height:1.25;"
            "margin-bottom:0.55rem;'>What Is Happening</div>"
            f"<div style='color:rgba(255,255,255,0.9);font-size:0.95rem;line-height:1.6;'>"
            f"{html.escape(summary or 'No incident summary available.')}</div>"
            "<div style='border-top:1px solid rgba(255,255,255,0.08);margin-top:0.8rem;"
            "padding-top:0.55rem;color:rgba(255,255,255,0.62);font-size:0.82rem;line-height:1.35;'>"
            f"{html.escape(observed)}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        with st.expander("Why This Color", expanded=False):
            st.write(build_color_reason(record))
        with st.expander("Other Data", expanded=False):
            st.markdown("**Timestamp**")
            st.write(str(record.get("timestamp", "")) or "Not available.")
            st.markdown("**Decision Reasoning Path**")
            render_decision_reasoning(record)
    return confirmed if show_confirm else False
