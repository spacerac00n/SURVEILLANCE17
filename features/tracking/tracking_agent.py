from __future__ import annotations

import json
import re
from datetime import datetime, timezone

import streamlit as st
from openai import OpenAI

from config import OPENAI_API_KEY_2, TRACKING_PROMPT_TEMPLATE, TRACKING_VLM_MODEL
from features.tracking.tracking_state import TrackingState


def _extract_payload(raw_text: str) -> dict[str, object]:
    """Parse JSON from raw model text, including fenced JSON blocks."""
    text = raw_text.strip()
    if not text:
        return {}
    for candidate in (text, text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _as_visible(value: object) -> bool:
    """Coerce model output into a visibility boolean."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "visible", "detected", "1"}


def _observe(frame_b64: str, prompt: str) -> dict[str, object]:
    """Return one Agent 2 VLM observation or a safe fallback."""
    if not OPENAI_API_KEY_2 or not frame_b64:
        return {
            "subject_visible": False,
            "last_position": "",
            "confidence": "low",
            "notes": "",
        }
    try:
        response = OpenAI(api_key=OPENAI_API_KEY_2).responses.create(
            model=TRACKING_VLM_MODEL,
            input=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Analyze this frame."},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/jpeg;base64,{frame_b64}",
                        },
                    ],
                },
            ],
        )
        payload = _extract_payload(str(getattr(response, "output_text", "")))
    except Exception:
        return {
            "subject_visible": False,
            "last_position": "",
            "confidence": "low",
            "notes": "",
        }
    return payload if isinstance(payload, dict) else {"subject_visible": False}


def start_tracking(initial_state: TrackingState) -> None:
    """Activate the Track Card state for the UI."""
    st.session_state["tracking"] = dict(initial_state)


def check_tracking_match(
    frame_b64: str,
    camera_id: str,
    frame_index: int,
    source_offset_seconds: float,
    fallback_detected: bool = False,
    fallback_description: str = "",
) -> None:
    """Run the Camera 2 tracking check and append positive sightings."""
    tracking = dict(st.session_state.get("tracking", {}))
    if not tracking or not tracking.get("active"):
        return
    if camera_id != str(tracking.get("search_camera_id", "")):
        return
    prompt = TRACKING_PROMPT_TEMPLATE.format(
        subject_description=tracking.get("subject_description", ""),
        user_extra_context=tracking.get("user_extra_context", ""),
    )
    observation = _observe(frame_b64, prompt)
    subject_visible = _as_visible(observation.get("subject_visible"))
    if not subject_visible and fallback_detected:
        observation = {
            **observation,
            "subject_visible": True,
            "last_position": str(observation.get("last_position", "")).strip() or "Visible in Camera 2 frame",
            "confidence": str(observation.get("confidence", "")).strip() or "low",
            "notes": str(observation.get("notes", "")).strip()
            or (
                "Tracking fallback used from Camera 2 threat detection."
                + (f" {fallback_description}" if fallback_description else "")
            ),
        }
        subject_visible = True
    if not subject_visible:
        return
    seen_at = datetime.now(timezone.utc).isoformat()
    sighting = {
        "camera_id": camera_id,
        "last_seen_camera": camera_id,
        "frame_index": frame_index,
        "source_offset_seconds": source_offset_seconds,
        "timestamp": seen_at,
        "last_seen_timestamp": seen_at,
        "last_position": str(observation.get("last_position", "")),
        "confidence": str(observation.get("confidence", "low")),
        "notes": str(observation.get("notes", "")),
    }
    tracking["sightings"] = list(tracking.get("sightings", [])) + [sighting]
    tracking["last_sighting"] = sighting
    st.session_state["tracking"] = tracking
