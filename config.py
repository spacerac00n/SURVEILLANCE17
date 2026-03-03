from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
BASE_DIR = Path(__file__).resolve().parent
CAMERA_PROFILE = {
    "camera_id": "cam-001",
    "location_name": "North Station Concourse",
    "zone_type": "transit",
    "coordinates": {"lat": 1.29027, "lng": 103.851959},
}
# Deprecated: crowd density is now estimated by the vision model.
CROWD_DENSITY_RULES = {
    (0, 6): "low",
    (6, 12): "medium",
    (12, 18): "high",
    (18, 24): "medium",
}
ESCALATION_RULES = {
    "none": {"low": 1, "medium": 1, "high": 1},
    "suspicious_behaviour": {"low": 1, "medium": 2, "high": 2},
    "physical_altercation": {"low": 2, "medium": 2, "high": 3},
    "weapon": {"low": 3, "medium": 3, "high": 3},
}
COLOR_CRITERIA = {
    "green": {
        "label": "Normal",
        "risk_range": [0.0, 3.0],
        "extreme_cases": [
            "Calm campus walk (students with backpacks)",
            "Normal lecture crowd dispersing",
            "Empty hall at night",
            "Gym class in progress",
        ],
        "cues": [
            "Crowd <30 people",
            "Typical NTU attire (T-shirt, shorts, sandals)",
            "Standard student bags only",
            "Natural walking/ chatting flow",
        ],
        "hex": "#00FF00",
    },
    "yellow": {
        "label": "Monitor",
        "risk_range": [3.1, 6.0],
        "extreme_cases": [
            "Someone sitting alone on bench >10min",
            "Large group loitering near hall entrance",
            "Person filming others without permission",
            "Multiple large bags left unattended",
        ],
        "cues": [
            "Crowd 30-70 people",
            "Slightly oversized bags",
            "1-2 people stationary >30s",
            "Jacket/hoodie in 30C heat (AC areas OK)",
        ],
        "hex": "#FFFF00",
    },
    "orange": {
        "label": "Alert",
        "risk_range": [6.1, 8.0],
        "extreme_cases": [
            "Person reaching into bag repeatedly",
            "Group forming tight circle (huddle)",
            "Individual backing away from crowd evasively",
            "Multiple people staring at one suspicious person",
        ],
        "cues": [
            "Crowd 70-120 people",
            "Bulky/hidden objects in clothing",
            "Heavy jackets/sweaters in hot weather",
            "3+ people stationary >1min",
            "Fast hand movements near waist/bags",
        ],
        "hex": "#FF8C00",
    },
    "red": {
        "label": "Critical",
        "risk_range": [8.1, 10.0],
        "extreme_cases": [
            "GUNS visible (long black object pointed at people)",
            "KNIFE STABBING (person lunging with blade motion)",
            "MASS PANIC (everyone running different directions)",
            "FIGHT ESCALATION (multiple people swinging fists)",
            "CROWD CRUSH (people falling/pushing pile-up)",
        ],
        "cues": [
            "Crowd >120 OR rapid surge",
            "Long rigid objects (bat/stick/gun silhouette)",
            "Face coverings + bulky clothing + evasive movement",
            "Multiple people sprinting chaotically",
            "Person holding object toward others threateningly",
        ],
        "hex": "#FF0000",
    },
}
THREAT_COLOR_ORDER = ("green", "yellow", "orange", "red")
COLOR_TO_ESCALATION_MODE = {"green": 1, "yellow": 1, "orange": 2, "red": 3}
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_API_KEY_2 = os.getenv("OPENAI_API_KEY_2")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_VISION_MODEL = os.getenv("OLLAMA_VISION_MODEL", "qwen3-vl:4b")
DATA_DIR = BASE_DIR / "data"
VIDEO_PATH = str(BASE_DIR / "demo1.mov")
FRAME_INTERVAL_SECONDS = 2.0
VLM_WORKER_COUNT = 3
TIMELINE_WINDOW_SIZE = 12
UI_REFRESH_SECONDS = 0.25
VISION_MODEL = "gpt-4.1"
AGENT_MODEL = "gpt-4.1"
TRACKING_VLM_MODEL = TRACKING_MODEL = "gpt-4o"
HARDCODED_CAMERAS = [
    {"camera_id": "CAM-WW", "name": "Camera WW", "status": "yellow"},
    {"camera_id": "CAM-XX", "name": "Camera XX", "status": "yellow"},
    {"camera_id": "CAM-YY", "name": "Camera YY", "status": "yellow"},
    {"camera_id": "CAM-ZZ", "name": "Camera ZZ", "status": "yellow"},
]
LIVE_CAMERAS = [
    {"camera_id": "CAM-LIVE-01", "name": "Camera 1"},
    {"camera_id": "CAM-LIVE-02", "name": "Camera 2"},
]
TRACKING_PROMPT_TEMPLATE = (
    "You are a surveillance tracking AI. Check whether this specific subject is visible in the frame. "
    "Original description: {subject_description} "
    "Operator context: {user_extra_context} "
    "Return only valid JSON: subject_visible (bool), last_position (str), "
    "confidence (high|medium|low), notes (str)"
)
TRACKING_FRAME_INTERVAL = 2
REACQUISITION_PROMPT_TEMPLATE = (
    "You are a surveillance tracking AI. Use this BOLO to reacquire the subject. "
    "BOLO: {bolo_text} Return only valid JSON: subject_visible (bool), "
    "last_position (str), confidence (high|medium|low), notes (str)"
)
BOLO_SYSTEM_PROMPT = "You are a law enforcement AI. Generate a structured BOLO report."
BOLO_USER_PROMPT_TEMPLATE = (
    "Tracking observations: {observations}\n"
    "Original subject: {subject_description}\n"
    "Operator notes: {user_extra_context}\n"
    "Generate BOLO in this exact format, no extra text:\n"
    "CONFIDENCE: (High/Medium/Low)\n"
    "SUBJECT: (gender, clothing, build, distinguishing features)\n"
    "LAST SEEN: (camera name and position)\n"
    "NOTES: (any important details, direction of movement, behaviour, threat level)"
)
BOLO_FALLBACK_TEXT = (
    "CONFIDENCE: Medium\n"
    "SUBJECT: Unknown — tracking data unavailable\n"
    "LAST SEEN: Camera 1\n"
    "NOTES: Manual follow-up required"
)


def build_color_criteria_prompt() -> str:
    """Return a compact scoring rubric for the vision model."""
    sections: list[str] = []
    for color in THREAT_COLOR_ORDER:
        criteria = COLOR_CRITERIA[color]
        risk_min, risk_max = criteria["risk_range"]
        cues = "; ".join(criteria["cues"][:3])
        extreme = "; ".join(criteria["extreme_cases"][:2])
        sections.append(
            f"{criteria['label']} ({color}, {risk_min}-{risk_max}): "
            f"cues={cues}. Examples={extreme}."
        )
    return " ".join(sections)


COLOR_CRITERIA_PROMPT = build_color_criteria_prompt()
VISION_SYSTEM_PROMPT = (
    "You are a security surveillance AI. Analyze the image carefully, look-out for people with potential threat or suspicious character, take note of how they dress as well and return only "
    "valid JSON with these fields: threat_detected (bool), threat_type "
    "(weapon | physical_altercation | suspicious_behaviour | none), "
    "confidence (high | medium | low), people_count (int), crowd_density "
    "(low | medium | high, estimated for the specific camera location), "
    "risk_score (float from 0.0 to 10.0), description (str, one sentence). "
    "Assign risk_score using this rubric: "
    f"{COLOR_CRITERIA_PROMPT}"
)
VISION_USER_PROMPT = (
    "Analyze this surveillance frame and estimate crowd density for the "
    "specific camera location. Include a backup risk score."
)
RISK_SYSTEM_PROMPT = (
    "You are a security risk scoring AI. Analyze the surveillance image and return "
    "only valid JSON with these fields: risk_score (float from 0.0 to 10.0), "
    "reasoning (str, one sentence). Assign risk_score using this rubric: "
    f"{COLOR_CRITERIA_PROMPT}"
)
RISK_USER_PROMPT = (
    "Review this surveillance frame and the detection context, then decide the "
    "final risk_score from 0.0 to 10.0."
)
ESCALATION_SYSTEM_PROMPT = (
    "You are a security escalation AI. Return valid JSON with "
    "incident_summary and recommended_action."
)
# Deprecated: the dashboard now resolves colors from COLOR_CRITERIA.
ALERT_COLORS = {"safe": "green", "watch": "orange", "critical": "red"}
WAITING_SUMMARY = "Waiting for the next sampled frame."
WAITING_ACTION = "Add a demo MP4 at VIDEO_PATH to drive the loop."
