from __future__ import annotations

import streamlit as st

from config import HARDCODED_CAMERAS, LIVE_CAMERAS


def _status(camera_id: str, tracking: dict[str, object]) -> tuple[str, str, bool]:
    """Return the color, status text, and pulse state for one camera."""
    active = bool(tracking.get("active"))
    last_sighting = dict(tracking.get("last_sighting", {}))
    if camera_id and last_sighting.get("camera_id") == camera_id:
        return "#e74c3c", "TARGET SPOTTED", True
    if active and tracking.get("source_camera_id") == camera_id:
        return "#e67e22", "TRACK SOURCE", True
    if active and tracking.get("search_camera_id") == camera_id:
        return "#3498db", "TRACKING SEARCH", True
    if active:
        return "#f1c40f", "TRACKING MODE", True
    return "#2ecc71", "Monitoring", False


def _hardcoded() -> str:
    """Return the static hardcoded camera row HTML."""
    dots = []
    active = bool(st.session_state["tracking"]["active"])
    pulse = " pulse" if active else ""
    status = "TRACKING MODE" if active else "Monitoring"
    for camera in HARDCODED_CAMERAS:
        dots.append(
            "<div class='node'><div class='dot yellow"
            f"{pulse}'></div><div>{camera['name']}</div><small>{status}</small></div>"
        )
    return "".join(dots)


def _live_camera(camera: dict[str, str]) -> None:
    """Render one clickable live camera icon."""
    color, status, pulse = _status(camera["camera_id"], st.session_state["tracking"])
    key = f"cam_button_{camera['camera_id'].lower().replace('-', '_')}"
    pulse_css = "animation:pulse 1.2s infinite;" if pulse else ""
    st.markdown(f"<style>.st-key-{key} button{{width:40px;height:40px;border-radius:999px;border:none;background:{color};color:transparent;{pulse_css}}}</style>", unsafe_allow_html=True)
    if st.button("●", key=key):
        st.session_state["active_camera"] = camera["camera_id"]
        st.rerun()
    st.markdown(f"**{camera['name']}**  \n<small>{status}</small>", unsafe_allow_html=True)


def render_camera_map() -> None:
    """Render the global simulated camera map and navigation controls."""
    columns = max(len(HARDCODED_CAMERAS), 1)
    st.markdown(
        "<style>@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(231,76,60,.7)}"
        "50%{box-shadow:0 0 0 16px rgba(231,76,60,0)}}"
        f".map{{display:grid;grid-template-columns:repeat({columns},1fr);gap:18px}}"
        ".node{text-align:center}.dot{width:40px;height:40px;border-radius:999px;margin:0 auto 8px}"
        ".yellow{background:#f1c40f}.pulse{animation:pulse 1.2s infinite}</style>",
        unsafe_allow_html=True,
    )
    st.markdown(f"<div class='map'>{_hardcoded()}</div>", unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        _live_camera(LIVE_CAMERAS[0])
    with right:
        _live_camera(LIVE_CAMERAS[1])
