"""
Natural-Language Query Service
================================
Translates plain-English questions about traffic/vehicle data into DB queries
against the existing Detection, VehicleEvent, and TrajectoryCamera tables.

No external LLM required. Uses a deterministic intent parser (regex patterns)
that covers the 8 most useful query types for the demo. Each pattern maps to
an existing DB query — 100% reliable, zero hallucination risk.

Supported intents
-----------------
1. vehicles_at_location   "which vehicles [were at / crossed] [location]"
2. time_range             "vehicles between [TIME] and [TIME]"
3. recent                 "vehicles in the last [N] hours/minutes"
4. plate_lookup           "show me [PLATE]" / "find plate [PLATE]"
5. count_at_location      "how many vehicles at [location]"
6. suspicious             "suspicious vehicles" / "anomalies"
7. multi_camera           "vehicles seen at more than [N] cameras"
8. help                   "help" / "what can I ask" / unrecognised input

Location matching is fuzzy (case-insensitive substring on location_name,
road_name, and camera_id) — "ameerpet", "HITEC", "CAM_001" all resolve.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.detection import Detection
from app.models.trajectory_camera import TrajectoryCamera
from app.models.vehicle_event import VehicleEvent
from app.schemas.nl_query import NLQueryRequest, NLQueryResponse

logger = logging.getLogger(__name__)

# ── suggestion bank ───────────────────────────────────────────────────────────
_SUGGESTIONS = [
    "Which vehicles crossed Ameerpet Junction in the last hour?",
    "Show me vehicles between 6 PM and 7 PM",
    "How many vehicles at Begumpet in the last 2 hours?",
    "Find plate TS09AB1234",
    "Show suspicious vehicles",
    "Vehicles seen at more than 2 cameras",
    "Vehicles in the last 30 minutes",
]

# ── time-word helpers ─────────────────────────────────────────────────────────
_HOUR_WORDS  = {"hour": 1, "hours": 1, "hr": 1, "hrs": 1}
_MIN_WORDS   = {"minute": 1/60, "minutes": 1/60, "min": 1/60, "mins": 1/60}

def _parse_relative_hours(qty_str: str, unit: str) -> float:
    """'2 hours' → 2.0,  '30 minutes' → 0.5"""
    qty   = float(qty_str)
    unit  = unit.lower().rstrip("s")
    if unit in ("hour", "hr"):
        return qty
    if unit in ("minute", "min"):
        return qty / 60
    return qty

# clock like "6 PM", "18:00", "6:30 PM"
_CLOCK_RE = re.compile(
    r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?",
    re.IGNORECASE,
)

def _parse_clock(raw: str) -> Optional[datetime]:
    m = _CLOCK_RE.match(raw.strip())
    if not m:
        return None
    hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    now = datetime.now(timezone.utc)
    return now.replace(hour=hour, minute=minute, second=0, microsecond=0)


# ── location resolver ─────────────────────────────────────────────────────────

def _resolve_location(
    token: str,
    db   : Session,
) -> Tuple[Optional[List[str]], Optional[str]]:
    """
    Fuzzy-match a token against camera location_name, road_name, and camera_id.
    Returns (list_of_matching_camera_ids, human_label) or (None, None).
    """
    token_l = token.lower().strip()
    cams    = db.query(TrajectoryCamera).all()
    matches = []
    for c in cams:
        fields = [
            c.camera_id.lower(),
            c.location_name.lower(),
            (c.road_name or "").lower(),
        ]
        if any(token_l in f for f in fields):
            matches.append(c)

    if not matches:
        return None, None

    cam_ids = [c.camera_id for c in matches]
    label   = matches[0].location_name if len(matches) == 1 else f"{len(matches)} locations matching '{token}'"
    return cam_ids, label


# ── result row builders ───────────────────────────────────────────────────────

def _detection_rows(dets: List[Detection], cam_map: Dict[str, TrajectoryCamera]) -> List[Dict]:
    rows = []
    for d in dets:
        cam   = cam_map.get(d.camera_id)
        loc   = cam.location_name if cam else d.camera_id
        rows.append({
            "plate_number" : d.plate_number,
            "camera_id"    : d.camera_id,
            "location"     : loc,
            "timestamp"    : d.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "confidence"   : f"{(d.detection_confidence or 0)*100:.1f}%",
        })
    return rows


def _cam_map(db: Session) -> Dict[str, TrajectoryCamera]:
    return {c.camera_id: c for c in db.query(TrajectoryCamera).all()}


# ═════════════════════════════════════════════════════════════════════════════
# Intent handlers
# ═════════════════════════════════════════════════════════════════════════════

def _handle_plate_lookup(plate: str, db: Session) -> NLQueryResponse:
    plate_u = plate.upper()
    dets    = (
        db.query(Detection)
          .filter(Detection.plate_number.ilike(f"%{plate_u}%"))
          .order_by(Detection.timestamp.desc())
          .limit(50)
          .all()
    )
    cmap = _cam_map(db)
    rows = _detection_rows(dets, cmap)

    if not dets:
        answer = f"No detections found for plate '{plate_u}'."
    else:
        cams_seen = sorted({d.camera_id for d in dets})
        first_ts  = min(d.timestamp for d in dets).strftime("%Y-%m-%d %H:%M UTC")
        last_ts   = max(d.timestamp for d in dets).strftime("%Y-%m-%d %H:%M UTC")
        answer    = (
            f"Plate {plate_u} was detected {len(dets)} time(s) across "
            f"{len(cams_seen)} camera(s). "
            f"First seen {first_ts}, last seen {last_ts}."
        )

    return NLQueryResponse(
        question       = f"Find plate {plate}",
        interpreted_as = f"All detections for plate number containing '{plate_u}'",
        intent         = "plate_lookup",
        answer_text    = answer,
        columns        = ["plate_number", "camera_id", "location", "timestamp", "confidence"],
        rows           = rows,
        total_results  = len(dets),
        parameters     = {"plate": plate_u},
        confidence     = "HIGH",
        suggestions    = [
            f"Show suspicious vehicles",
            f"Vehicles seen at more than 2 cameras",
            f"Which cameras did {plate_u} visit?",
        ],
    )


def _handle_vehicles_at_location(
    location_token: str,
    hours         : float,
    db            : Session,
    time_label    : str = "",
) -> NLQueryResponse:
    cam_ids, loc_label = _resolve_location(location_token, db)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    if not cam_ids:
        return NLQueryResponse(
            question       = f"Vehicles at {location_token}",
            interpreted_as = f"Location lookup for '{location_token}'",
            intent         = "vehicles_at_location",
            answer_text    = (
                f"Could not find a camera matching '{location_token}'. "
                f"Try: Ameerpet, Begumpet, Hitech City, Charminar, Secunderabad, "
                f"Madhapur, Kukatpally, LB Nagar, Mehdipatnam, Paradise, Kondapur."
            ),
            confidence     = "LOW",
            suggestions    = _SUGGESTIONS[:4],
        )

    dets = (
        db.query(Detection)
          .filter(
              Detection.camera_id.in_(cam_ids),
              Detection.timestamp >= cutoff,
          )
          .order_by(Detection.timestamp.desc())
          .limit(100)
          .all()
    )
    cmap = _cam_map(db)
    rows = _detection_rows(dets, cmap)

    tl = time_label or f"the last {hours:.0f}h" if hours < 24 else f"the last {hours/24:.0f} day(s)"
    if not dets:
        answer = f"No vehicles detected at {loc_label} in {tl}."
    else:
        plates = sorted({d.plate_number for d in dets})
        answer = (
            f"{len(dets)} detection(s) ({len(plates)} unique plate(s)) "
            f"at {loc_label} in {tl}."
        )

    return NLQueryResponse(
        question       = f"Vehicles at {location_token}",
        interpreted_as = f"Vehicles at {loc_label} ({', '.join(cam_ids)}) in {tl}",
        intent         = "vehicles_at_location",
        answer_text    = answer,
        columns        = ["plate_number", "camera_id", "location", "timestamp", "confidence"],
        rows           = rows,
        total_results  = len(dets),
        parameters     = {"camera_ids": cam_ids, "location": loc_label, "window_hours": hours},
        confidence     = "HIGH",
        suggestions    = [
            f"How many vehicles at {location_token} in the last 24 hours?",
            "Show suspicious vehicles",
            "Vehicles in the last 30 minutes",
        ],
    )


def _handle_count_at_location(
    location_token: str,
    hours         : float,
    db            : Session,
) -> NLQueryResponse:
    cam_ids, loc_label = _resolve_location(location_token, db)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    if not cam_ids:
        return NLQueryResponse(
            question       = f"Count at {location_token}",
            interpreted_as = f"Vehicle count for '{location_token}'",
            intent         = "count_at_location",
            answer_text    = f"Could not find a camera matching '{location_token}'.",
            confidence     = "LOW",
            suggestions    = _SUGGESTIONS[:4],
        )

    total = (
        db.query(func.count(Detection.id))
          .filter(Detection.camera_id.in_(cam_ids), Detection.timestamp >= cutoff)
          .scalar() or 0
    )
    unique = (
        db.query(func.count(func.distinct(Detection.plate_number)))
          .filter(Detection.camera_id.in_(cam_ids), Detection.timestamp >= cutoff)
          .scalar() or 0
    )
    tl    = f"last {hours:.0f}h" if hours < 24 else f"last {hours/24:.0f} day(s)"
    answer = f"{total} vehicle detection(s) ({unique} unique plates) at {loc_label} in the {tl}."

    return NLQueryResponse(
        question       = f"Count at {location_token}",
        interpreted_as = f"Vehicle count at {loc_label} ({', '.join(cam_ids)}) in the {tl}",
        intent         = "count_at_location",
        answer_text    = answer,
        columns        = [],
        rows           = [],
        total_results  = total,
        parameters     = {"camera_ids": cam_ids, "location": loc_label, "window_hours": hours},
        confidence     = "HIGH",
        suggestions    = [
            f"Show me the vehicles at {location_token}",
            "Which location has the most traffic?",
            "Vehicles in the last hour",
        ],
    )


def _handle_recent(hours: float, db: Session) -> NLQueryResponse:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    dets   = (
        db.query(Detection)
          .filter(Detection.timestamp >= cutoff)
          .order_by(Detection.timestamp.desc())
          .limit(100)
          .all()
    )
    cmap   = _cam_map(db)
    rows   = _detection_rows(dets, cmap)
    plates = sorted({d.plate_number for d in dets})
    label  = f"{hours*60:.0f} minutes" if hours < 1 else f"{hours:.0f} hour(s)"

    if not dets:
        answer = f"No vehicles detected in the last {label}."
    else:
        answer = (
            f"{len(dets)} detection(s) ({len(plates)} unique plate(s)) "
            f"across the network in the last {label}."
        )

    return NLQueryResponse(
        question       = f"Vehicles in the last {label}",
        interpreted_as = f"All detections in the last {label} across all cameras",
        intent         = "recent",
        answer_text    = answer,
        columns        = ["plate_number", "camera_id", "location", "timestamp", "confidence"],
        rows           = rows,
        total_results  = len(dets),
        parameters     = {"window_hours": hours},
        confidence     = "HIGH",
        suggestions    = [
            "Vehicles at Ameerpet in the last hour",
            "Show suspicious vehicles",
            "How many vehicles at Begumpet in the last 2 hours?",
        ],
    )


def _handle_time_range(t_from: datetime, t_to: datetime, db: Session) -> NLQueryResponse:
    dets = (
        db.query(Detection)
          .filter(Detection.timestamp >= t_from, Detection.timestamp <= t_to)
          .order_by(Detection.timestamp.asc())
          .limit(100)
          .all()
    )
    cmap  = _cam_map(db)
    rows  = _detection_rows(dets, cmap)
    fmt   = "%H:%M"
    label = f"{t_from.strftime(fmt)} – {t_to.strftime(fmt)} UTC"

    if not dets:
        answer = f"No detections found between {label}."
    else:
        plates = sorted({d.plate_number for d in dets})
        answer = (
            f"{len(dets)} detection(s) ({len(plates)} unique plate(s)) "
            f"between {label}."
        )

    return NLQueryResponse(
        question       = f"Vehicles between {t_from.strftime(fmt)} and {t_to.strftime(fmt)}",
        interpreted_as = f"All detections from {t_from.isoformat()} to {t_to.isoformat()}",
        intent         = "time_range",
        answer_text    = answer,
        columns        = ["plate_number", "camera_id", "location", "timestamp", "confidence"],
        rows           = rows,
        total_results  = len(dets),
        parameters     = {"from": t_from.isoformat(), "to": t_to.isoformat()},
        confidence     = "HIGH",
        suggestions    = [
            "Vehicles in the last 2 hours",
            "Show suspicious vehicles",
        ],
    )


def _handle_suspicious(db: Session) -> NLQueryResponse:
    from app.trajectory.engine import reconstruct
    from app.trajectory.anomaly import MovementStatus
    from sqlalchemy import func as _f

    # Plates at >=2 cameras — candidates for trajectory anomaly
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    multi  = (
        db.query(Detection.plate_number)
          .filter(Detection.timestamp >= cutoff)
          .group_by(Detection.plate_number)
          .having(_f.count(_f.distinct(Detection.camera_id)) >= 2)
          .all()
    )

    suspicious_rows: List[Dict] = []
    for (plate,) in multi[:10]:
        try:
            traj = reconstruct(db, plate)
        except Exception:
            continue
        if traj.status in (MovementStatus.SUSPICIOUS, MovementStatus.IMPOSSIBLE):
            suspicious_rows.append({
                "plate_number"  : plate,
                "status"        : traj.status.value,
                "cameras"       : " → ".join(traj.statistics.cameras_visited),
                "avg_speed_kmh" : f"{traj.statistics.average_speed_kmh:.1f} km/h",
                "distance_km"   : f"{traj.statistics.total_distance_km:.2f} km",
                "first_seen"    : traj.statistics.first_seen.strftime("%H:%M UTC") if traj.statistics.first_seen else "—",
                "last_seen"     : traj.statistics.last_seen.strftime("%H:%M UTC")  if traj.statistics.last_seen  else "—",
            })

    if not suspicious_rows:
        answer = "No suspicious or impossible vehicle trajectories found in the last 24 hours."
    else:
        answer = (
            f"{len(suspicious_rows)} vehicle(s) with suspicious or impossible "
            f"trajectories detected in the last 24 hours."
        )

    return NLQueryResponse(
        question       = "Suspicious vehicles",
        interpreted_as = "Vehicles with SUSPICIOUS or IMPOSSIBLE trajectory status in last 24h",
        intent         = "suspicious",
        answer_text    = answer,
        columns        = ["plate_number", "status", "cameras", "avg_speed_kmh", "distance_km", "first_seen", "last_seen"],
        rows           = suspicious_rows,
        total_results  = len(suspicious_rows),
        parameters     = {"window_hours": 24, "min_cameras": 2},
        confidence     = "HIGH",
        suggestions    = [
            "Find plate TS09AB1234",
            "Vehicles seen at more than 2 cameras",
            "Show vehicles in the last hour",
        ],
    )


def _handle_multi_camera(min_cameras: int, db: Session) -> NLQueryResponse:
    from sqlalchemy import func as _f

    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    rows_q = (
        db.query(
            Detection.plate_number,
            _f.count(_f.distinct(Detection.camera_id)).label("cam_count"),
            _f.count(Detection.id).label("total"),
            _f.min(Detection.timestamp).label("first_seen"),
            _f.max(Detection.timestamp).label("last_seen"),
        )
        .filter(Detection.timestamp >= cutoff)
        .group_by(Detection.plate_number)
        .having(_f.count(_f.distinct(Detection.camera_id)) >= min_cameras)
        .order_by(_f.count(_f.distinct(Detection.camera_id)).desc())
        .all()
    )

    cmap = _cam_map(db)
    result_rows = []
    for r in rows_q:
        # get camera sequence
        seq = (
            db.query(Detection.camera_id, Detection.timestamp)
              .filter(Detection.plate_number == r.plate_number,
                      Detection.timestamp >= cutoff)
              .order_by(Detection.timestamp.asc())
              .all()
        )
        cam_seq = " → ".join(
            cmap[s.camera_id].location_name if s.camera_id in cmap else s.camera_id
            for s in seq
        )
        result_rows.append({
            "plate_number": r.plate_number,
            "cameras_visited": r.cam_count,
            "route": cam_seq,
            "total_detections": r.total,
            "first_seen": r.first_seen.strftime("%H:%M UTC"),
            "last_seen" : r.last_seen.strftime("%H:%M UTC"),
        })

    if not result_rows:
        answer = f"No vehicles found at {min_cameras}+ cameras in the last 24 hours."
    else:
        answer = (
            f"{len(result_rows)} vehicle(s) appeared at {min_cameras} or more "
            f"cameras in the last 24 hours."
        )

    return NLQueryResponse(
        question       = f"Vehicles seen at more than {min_cameras} cameras",
        interpreted_as = f"Plates with detections at >= {min_cameras} distinct cameras in last 24h",
        intent         = "multi_camera",
        answer_text    = answer,
        columns        = ["plate_number", "cameras_visited", "route", "total_detections", "first_seen", "last_seen"],
        rows           = result_rows,
        total_results  = len(result_rows),
        parameters     = {"min_cameras": min_cameras, "window_hours": 24},
        confidence     = "HIGH",
        suggestions    = [
            "Show suspicious vehicles",
            "Find plate TS09AB1234",
            "Vehicles in the last hour",
        ],
    )


def _handle_help() -> NLQueryResponse:
    examples = [
        "Which vehicles crossed Ameerpet Junction in the last hour?",
        "Show vehicles between 6 PM and 7 PM",
        "How many vehicles at Begumpet in the last 2 hours?",
        "Find plate TS09AB1234",
        "Show suspicious vehicles",
        "Vehicles seen at more than 2 cameras",
        "Vehicles in the last 30 minutes",
        "Which cameras did TS09AB1234 visit?",
    ]
    return NLQueryResponse(
        question       = "help",
        interpreted_as = "Help request — showing supported query types",
        intent         = "help",
        answer_text    = (
            "You can ask questions about vehicle detections in plain English. "
            "Try one of the examples below."
        ),
        columns        = ["Example question"],
        rows           = [{"Example question": e} for e in examples],
        total_results  = len(examples),
        parameters     = {},
        confidence     = "HIGH",
        suggestions    = examples[:4],
    )


# ═════════════════════════════════════════════════════════════════════════════
# Main dispatcher
# ═════════════════════════════════════════════════════════════════════════════

def process_nl_query(request: NLQueryRequest, db: Session) -> NLQueryResponse:
    """
    Parse a natural-language question and route to the correct handler.

    Pattern matching is case-insensitive and order-dependent — more specific
    patterns are checked before general ones.
    """
    q = request.question.strip()
    ql = q.lower()

    logger.info("[NLQuery] Question: %r", q)

    # ── 1. Help ───────────────────────────────────────────────────────────────
    if re.search(r"\bhelp\b|what can i ask|what (can|do) you|examples", ql):
        return _handle_help()

    # ── 2. Plate lookup ───────────────────────────────────────────────────────
    # "find plate TS09AB1234" / "show me MH12XY5678" / "which cameras did TS... visit"
    plate_m = re.search(
        r"(?:find|show|lookup|search|track|where is|cameras.*did|did.*cameras)\s+(?:plate\s+)?([A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4})",
        q, re.IGNORECASE,
    )
    if not plate_m:
        # bare plate-like token anywhere in the string
        plate_m = re.search(r"\b([A-Z]{2}\d{1,2}[A-Z]{1,3}\d{1,4})\b", q, re.IGNORECASE)
    if plate_m:
        return _handle_plate_lookup(plate_m.group(1), db)

    # ── 3. Suspicious / anomaly ───────────────────────────────────────────────
    if re.search(r"\b(suspicious|anomal|impossible|fast.moving|speeding)\b", ql):
        return _handle_suspicious(db)

    # ── 4. Multi-camera ───────────────────────────────────────────────────────
    mc_m = re.search(
        r"(?:seen|spotted|detected|appear|visit|cross)\s+(?:at\s+)?(?:more than|more|over|>)\s*(\d+)\s+camera",
        ql,
    )
    if not mc_m:
        mc_m = re.search(r"(\d+)\s*\+?\s*cameras?", ql)
    if mc_m:
        return _handle_multi_camera(int(mc_m.group(1)), db)

    # ── 5. Count at location ──────────────────────────────────────────────────
    count_loc_m = re.search(
        r"how many\s+(?:vehicles?|cars?|detections?)?(?:\s+(?:were\s+)?(?:at|in|near|seen at|detected at|crossed?))?\s+([a-z0-9 \-]+?)\s+(?:in\s+the\s+last\s+|in\s+last\s+|last\s+)?(\d+(?:\.\d+)?)\s+(hour|hours|hr|hrs|minute|minutes|min|mins)",
        ql,
    )
    if not count_loc_m:
        count_loc_m = re.search(
            r"how many\s+(?:vehicles?|cars?|detections?)?\s+(?:at|in|near|detected at|seen at)\s+([a-z0-9 \-]+)",
            ql,
        )
    if count_loc_m:
        location = count_loc_m.group(1).strip()
        hours    = 1.0
        if count_loc_m.lastindex and count_loc_m.lastindex >= 3:
            try:
                hours = _parse_relative_hours(count_loc_m.group(2), count_loc_m.group(3))
            except Exception:
                hours = 1.0
        return _handle_count_at_location(location, hours, db)

    # ── 6. Time range ─────────────────────────────────────────────────────────
    tr_m = re.search(
        r"between\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)\s+and\s+(\d{1,2}(?::\d{2})?\s*(?:am|pm)?)",
        ql,
    )
    if tr_m:
        t_from = _parse_clock(tr_m.group(1))
        t_to   = _parse_clock(tr_m.group(2))
        if t_from and t_to:
            return _handle_time_range(t_from, t_to, db)

    # ── 7. Recent (no location) ───────────────────────────────────────────────
    recent_m = re.search(
        r"(?:in\s+)?(?:the\s+)?last\s+(\d+(?:\.\d+)?)\s+(hour|hours|hr|hrs|minute|minutes|min|mins)",
        ql,
    )
    # Only treat as "recent" if there is no location preposition OTHER than
    # the time fragment itself (e.g. "vehicles IN THE LAST 30 minutes" has no
    # real location — the "in" belongs to the time phrase)
    has_location_phrase = bool(re.search(
        r"\b(?:at|near|junction|road|signal|gate|circle|stop|plaza|station|underpass|flyover|nagar|pally|bowli|patnam|nakar|camp|banjara|punjagutta|ameerpet|begumpet|hitech|gachibowli|madhapur|kondapur|charminar|uppal|dilsukhnagar|paradise|mehdipatnam|tolichowki|secunderabad|kukatpally)\b",
        ql,
    ))
    if recent_m and not has_location_phrase:
        hours = _parse_relative_hours(recent_m.group(1), recent_m.group(2))
        return _handle_recent(hours, db)

    # ── 8. Vehicles at location (with optional time window) ───────────────────
    # Patterns: "vehicles at X", "which vehicles crossed X", "who was at X in last N hours"
    loc_time_m = re.search(
        r"(?:vehicles?|cars?|who|which|show(?:\s+me)?|list|what|display)\s+(?:were\s+)?(?:at|in|near|crossed?|spotted at|detected at|passed through|seen at|on)\s+([a-z0-9 \-]+?)\s+(?:in\s+(?:the\s+)?last\s+)?(\d+(?:\.\d+)?)\s+(hour|hours|hr|hrs|minute|minutes|min|mins)",
        ql,
    )
    if loc_time_m:
        location = loc_time_m.group(1).strip()
        # Reject if location looks like a time fragment
        if not re.match(r"^(the|last|in|a|an|\d)$", location):
            hours = _parse_relative_hours(loc_time_m.group(2), loc_time_m.group(3))
            return _handle_vehicles_at_location(location, hours, db)

    loc_m = re.search(
        r"(?:vehicles?|cars?|who|which|show(?:\s+me)?|list|what|display)\s+(?:were\s+)?(?:at|in|near|crossed?|spotted at|detected at|passed through|seen at|on)\s+([a-z0-9 \-]+)",
        ql,
    )
    if loc_m:
        location = loc_m.group(1).strip()
        # Reject time fragments grabbed as location names
        if not re.match(r"^(the|last|in|a|an|\d)", location):
            time_m = re.search(r"(?:in\s+(?:the\s+)?last\s+)?(\d+(?:\.\d+)?)\s+(hour|hours|hr|hrs|minute|minutes|min|mins)", ql)
            hours  = _parse_relative_hours(time_m.group(1), time_m.group(2)) if time_m else 24.0
            return _handle_vehicles_at_location(location, hours, db)

    # Bare recent pattern with location present — catch "last N hours at X"
    if recent_m:
        hours    = _parse_relative_hours(recent_m.group(1), recent_m.group(2))
        loc_bare = re.search(r"\b(?:at|in|near)\s+([a-z0-9 \-]+)", ql)
        if loc_bare:
            return _handle_vehicles_at_location(loc_bare.group(1).strip(), hours, db)
        return _handle_recent(hours, db)

    # ── Fallback: help ────────────────────────────────────────────────────────
    resp           = _handle_help()
    resp.question  = q
    resp.interpreted_as = f"Could not parse '{q}' — showing help"
    resp.answer_text    = (
        f"I didn't understand '{q}'. "
        "Try asking about a specific location, time window, or plate number. "
        "See the examples below."
    )
    resp.confidence = "LOW"
    return resp
