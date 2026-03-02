from __future__ import annotations

import html
from datetime import datetime

import streamlit as st


_OPEN_KEY = "police_chat_open"
_MESSAGES_KEY = "police_chat_messages"
_RED_ALERT_SENT_KEY = "police_chat_red_alert_sent"


def _ensure_state() -> None:
    """Initialize local chat state without depending on dashboard flow state."""
    st.session_state.setdefault(_OPEN_KEY, False)
    st.session_state.setdefault(_MESSAGES_KEY, [])
    st.session_state.setdefault(_RED_ALERT_SENT_KEY, False)


def _toggle() -> None:
    """Toggle the chat panel open state."""
    st.session_state[_OPEN_KEY] = not bool(st.session_state.get(_OPEN_KEY, False))


def _humanize_threat(threat_type: str) -> str:
    """Return a readable threat label for alert messages."""
    cleaned = threat_type.replace("_", " ").strip()
    return cleaned.title() if cleaned else "Unknown"


def _alert_timestamp() -> str:
    """Return the local display time for a new alert."""
    return datetime.now().astimezone().strftime("%I:%M %p").lstrip("0")


def notify_red_threat(
    incident: dict[str, object],
    camera_label: str,
) -> None:
    """Append only the first red-priority notification for the session."""
    _ensure_state()
    if str(incident.get("threat_color", "")).strip().lower() != "red":
        return
    case_id = str(incident.get("case_id", "")).strip() or f"frame-{int(incident.get('frame_index', 0))}"
    if bool(st.session_state.get(_RED_ALERT_SENT_KEY, False)):
        return
    threat = _humanize_threat(str(incident.get("threat_type", "none")))
    priority = str(incident.get("threat_label", "")).strip() or "Critical"
    messages = list(st.session_state.get(_MESSAGES_KEY, []))
    messages.append(
        {
            "role": "alert",
            "camera_label": str(camera_label),
            "case_id": case_id,
            "threat": threat,
            "priority": priority,
            "created_at": _alert_timestamp(),
        }
    )
    st.session_state[_MESSAGES_KEY] = messages[-10:]
    st.session_state[_RED_ALERT_SENT_KEY] = True
    st.session_state[_OPEN_KEY] = True


def render_police_chat() -> None:
    """Render the self-contained police dispatch chat in the sidebar."""
    _ensure_state()
    st.sidebar.markdown(
        """
        <style>
        .st-key-police_chat_toggle button{
            width:44px;
            height:44px;
            border-radius:999px;
            border:1px solid rgba(27,53,88,.18);
            background:linear-gradient(180deg,#183a67 0%,#0f2748 100%);
            color:#eef5ff;
            font-weight:800;
            letter-spacing:.08em;
            box-shadow:0 8px 18px rgba(5,16,34,.18);
            padding:0;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
    icon_col, title_col = st.sidebar.columns((1, 4))
    with icon_col:
        if st.button("POL", key="police_chat_toggle", help="Police dispatch chat"):
            _toggle()
            st.rerun()
    with title_col:
        st.markdown(
            "<div style='font-size:1.2rem;font-weight:800;line-height:1.2;'>Notification</div>",
            unsafe_allow_html=True,
        )
    if not st.session_state.get(_OPEN_KEY):
        return
    messages = list(st.session_state.get(_MESSAGES_KEY, []))
    if not messages:
        st.sidebar.info("No active notifications.")
    else:
        for entry in messages:
            role = str(entry.get("role", ""))
            if role == "alert":
                camera_label = html.escape(str(entry.get("camera_label", "Unknown camera")))
                case_id = html.escape(str(entry.get("case_id", "unknown-case")))
                threat = html.escape(str(entry.get("threat", "Unknown")))
                priority = html.escape(str(entry.get("priority", "Critical")))
                created_at = html.escape(str(entry.get("created_at", "")))
                st.sidebar.markdown(
                    "<div style='padding:0.85rem 0.95rem;margin:0.4rem 0 0.7rem;"
                    "border-radius:0.75rem;border:1px solid rgba(255,59,48,0.75);"
                    "background:#000000;color:#ffffff;'>"
                    f"<p style='margin:0 0 0.35rem;line-height:1.5;font-weight:800;'>🔴 {camera_label}</p>"
                    f"<p style='margin:0 0 0.35rem;line-height:1.5;font-weight:700;color:#ffffff;'>{case_id}</p>"
                    f"<p style='margin:0 0 0.2rem;line-height:1.55;color:#ffffff;'>Threat type: {threat}</p>"
                    f"<p style='margin:0;line-height:1.55;color:#ffffff;'>Priority: {priority}</p>"
                    f"<div style='margin-top:0.65rem;padding-top:0.5rem;"
                    "border-top:1px solid rgba(255,255,255,0.18);font-size:0.78rem;"
                    "line-height:1.3;color:rgba(255,255,255,0.72);text-align:right;'>"
                    f"{created_at}</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                continue
            content = html.escape(str(entry.get("content", "")))
            st.sidebar.markdown(
                "<div style='padding:0.8rem 0.9rem;margin:0.4rem 0 0.7rem;"
                "border-radius:0.75rem;border:1px solid rgba(255,255,255,0.14);"
                "background:#000000;color:#ffffff;'>"
                f"<p style='margin:0;line-height:1.55;'>{content}</p>"
                "</div>",
                unsafe_allow_html=True,
            )
