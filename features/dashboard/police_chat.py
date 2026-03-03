from __future__ import annotations

import html
import re
from datetime import datetime

import streamlit as st


_OPEN_KEY = "police_chat_open"
_MESSAGES_KEY = "police_chat_messages"
_RED_ALERT_SENT_KEY = "police_chat_red_alert_sent"
_TRACKER_ALERT_TOKENS_KEY = "police_chat_tracker_alert_tokens"
_DISPATCH_ALERT_TOKENS_KEY = "police_chat_dispatch_alert_tokens"
_SHAKE_SECONDS = 4.0


def _ensure_state() -> None:
    """Initialize local chat state without depending on dashboard flow state."""
    st.session_state.setdefault(_OPEN_KEY, False)
    st.session_state.setdefault(_MESSAGES_KEY, [])
    st.session_state.setdefault(_RED_ALERT_SENT_KEY, False)
    st.session_state.setdefault(_TRACKER_ALERT_TOKENS_KEY, [])
    st.session_state.setdefault(_DISPATCH_ALERT_TOKENS_KEY, [])


def _push_message(entry: dict[str, object]) -> None:
    """Insert a new notification at the top of the chat."""
    messages = list(st.session_state.get(_MESSAGES_KEY, []))
    st.session_state[_MESSAGES_KEY] = [entry, *messages][:10]


def _toggle() -> None:
    """Toggle the chat panel open state."""
    st.session_state[_OPEN_KEY] = not bool(st.session_state.get(_OPEN_KEY, False))


def _humanize_threat(threat_type: str) -> str:
    """Return a readable threat label for alert messages."""
    cleaned = threat_type.replace("_", " ").strip()
    return cleaned.title() if cleaned else "Unknown"


def _alert_metadata() -> dict[str, object]:
    """Return display and animation timing metadata for a new alert."""
    now = datetime.now().astimezone()
    return {
        "created_at": now.strftime("%I:%M %p").lstrip("0"),
        "created_at_epoch": now.timestamp(),
    }


def _camera_number(camera_id: str) -> str:
    """Return a compact camera number for tracker alerts."""
    matches = re.findall(r"\d+", camera_id)
    if not matches:
        return camera_id or "Unknown"
    return matches[-1].lstrip("0") or "0"


def _confidence_percent(confidence: object) -> str:
    """Convert model confidence labels into the requested percentage display."""
    text = str(confidence).strip().lower()
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


def _shake_class(entry: dict[str, object]) -> str:
    """Return the CSS class for newly raised notifications."""
    try:
        created_at_epoch = float(entry.get("created_at_epoch", 0.0))
    except (TypeError, ValueError):
        return ""
    if created_at_epoch <= 0:
        return ""
    age_seconds = datetime.now().astimezone().timestamp() - created_at_epoch
    return " police-chat-alert-shake" if 0.0 <= age_seconds <= _SHAKE_SECONDS else ""


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
    _push_message(
        {
            "role": "alert",
            "camera_label": str(camera_label),
            "case_id": case_id,
            "threat": threat,
            "priority": priority,
            **_alert_metadata(),
        }
    )
    st.session_state[_RED_ALERT_SENT_KEY] = True
    st.session_state[_OPEN_KEY] = True


def notify_tracker_match(
    camera_id: str,
    frame_index: int,
    confidence: object,
    threat_type: str,
) -> None:
    """Append one tracker notification for a newly confirmed sighting."""
    _ensure_state()
    token = f"{camera_id}:{frame_index}"
    seen_tokens = set(str(value) for value in st.session_state.get(_TRACKER_ALERT_TOKENS_KEY, []))
    if token in seen_tokens:
        return
    _push_message(
        {
            "role": "tracker",
            "confidence": _confidence_percent(confidence),
            "camera_number": _camera_number(camera_id),
            **_alert_metadata(),
            "threat_type": _humanize_threat(threat_type),
        }
    )
    st.session_state[_TRACKER_ALERT_TOKENS_KEY] = list(seen_tokens | {token})
    st.session_state[_OPEN_KEY] = True


def notify_dispatch_sent(case_id: str) -> None:
    """Append one notification when dispatch is confirmed for an incident."""
    _ensure_state()
    normalized_case_id = str(case_id).strip() or "dispatch"
    seen_tokens = set(str(value) for value in st.session_state.get(_DISPATCH_ALERT_TOKENS_KEY, []))
    if normalized_case_id in seen_tokens:
        return
    _push_message(
        {
            "role": "dispatch_sent",
            "content": "Dispatch Sent 🚨",
            "case_id": normalized_case_id,
            **_alert_metadata(),
        }
    )
    st.session_state[_DISPATCH_ALERT_TOKENS_KEY] = list(seen_tokens | {normalized_case_id})
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
        .police-chat-alert{
            transform-origin:center;
            will-change:transform, box-shadow;
        }
        .police-chat-alert-shake{
            animation:police-chat-alert-shake .38s ease-in-out 10;
        }
        @keyframes police-chat-alert-shake{
            0%,100%{transform:translateX(0);}
            15%{transform:translateX(-4px) rotate(-1deg);}
            35%{transform:translateX(4px) rotate(1deg);}
            55%{transform:translateX(-3px) rotate(-0.8deg);}
            75%{transform:translateX(3px) rotate(0.8deg);}
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
            "<div style='font-size:1.2rem;font-weight:800;line-height:1.2;'>NTU Security</div>",
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
            shake_class = _shake_class(entry)
            if role == "alert":
                camera_label = html.escape(str(entry.get("camera_label", "Unknown camera")))
                case_id = html.escape(str(entry.get("case_id", "unknown-case")))
                threat = html.escape(str(entry.get("threat", "Unknown")))
                priority = html.escape(str(entry.get("priority", "Critical")))
                created_at = html.escape(str(entry.get("created_at", "")))
                st.sidebar.markdown(
                    f"<div class='police-chat-alert{shake_class}' style='padding:0.85rem 0.95rem;margin:0.4rem 0 0.7rem;"
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
            if role == "tracker":
                confidence = html.escape(str(entry.get("confidence", "25%")))
                camera_number = html.escape(str(entry.get("camera_number", "Unknown")))
                created_at = html.escape(str(entry.get("created_at", "")))
                threat_type = html.escape(str(entry.get("threat_type", "Unknown")))
                st.sidebar.markdown(
                    f"<div class='police-chat-alert{shake_class}' style='padding:0.85rem 0.95rem;margin:0.4rem 0 0.7rem;"
                    "border-radius:0.75rem;border:1px solid rgba(255,255,255,0.16);"
                    "background:#000000;color:#ffffff;'>"
                    "<p style='margin:0 0 0.35rem;line-height:1.5;font-weight:800;'>‼️ Tracker</p>"
                    f"<p style='margin:0 0 0.2rem;line-height:1.55;color:#ffffff;'>Confidence: {confidence}</p>"
                    f"<p style='margin:0 0 0.2rem;line-height:1.55;color:#ffffff;'>Camera: {camera_number}</p>"
                    f"<p style='margin:0 0 0.2rem;line-height:1.55;color:#ffffff;'>Time: {created_at}</p>"
                    f"<p style='margin:0;line-height:1.55;color:#ffffff;'>Threat type: {threat_type}</p>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                continue
            if role == "dispatch_sent":
                content = html.escape(str(entry.get("content", "Dispatch Sent 🚨")))
                case_id = html.escape(str(entry.get("case_id", "")))
                created_at = html.escape(str(entry.get("created_at", "")))
                st.sidebar.markdown(
                    f"<div class='police-chat-alert{shake_class}' style='padding:0.85rem 0.95rem;margin:0.4rem 0 0.7rem;"
                    "border-radius:0.75rem;border:1px solid rgba(239,68,68,0.45);"
                    "background:#000000;color:#ffffff;'>"
                    f"<p style='margin:0;line-height:1.5;font-weight:800;color:#ffffff;'>{content}</p>"
                    f"<p style='margin:0.28rem 0 0;line-height:1.45;color:rgba(255,255,255,0.82);'>{case_id}</p>"
                    f"<div style='margin-top:0.55rem;padding-top:0.45rem;"
                    "border-top:1px solid rgba(255,255,255,0.12);font-size:0.78rem;"
                    "line-height:1.3;color:rgba(255,255,255,0.72);text-align:right;'>"
                    f"{created_at}</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )
                continue
            content = html.escape(str(entry.get("content", "")))
            st.sidebar.markdown(
                f"<div class='police-chat-alert{shake_class}' style='padding:0.8rem 0.9rem;margin:0.4rem 0 0.7rem;"
                "border-radius:0.75rem;border:1px solid rgba(255,255,255,0.14);"
                "background:#000000;color:#ffffff;'>"
                f"<p style='margin:0;line-height:1.55;'>{content}</p>"
                "</div>",
                unsafe_allow_html=True,
            )
