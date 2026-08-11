import csv
import glob
import json
import logging
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent.parent / "Google Health"
GLOBAL_EXPORT = DATA_DIR / "Global Export Data"

# In-process cache — this data only exists locally and doesn't change during
# a run, so there's no need to re-parse tens of thousands of rows per request.
_cache = {}


def available() -> bool:
    return DATA_DIR.is_dir()


def get_dashboard_data() -> dict:
    if "all" in _cache:
        return _cache["all"]

    data = {
        "weight": _load_weight(),
        "steps": _load_steps_daily(),
        "sleep": _load_sleep_score(),
        "nutrition": _load_nutrition(),
    }
    _cache["all"] = data
    return data


def _load_weight() -> list:
    """Weight log entries, converted from lbs (the Fitbit export's unit for
    this account, confirmed via the accompanying BMI values) to kg."""
    entries = []
    for path in sorted(GLOBAL_EXPORT.glob("weight-*.json")):
        try:
            for e in json.loads(path.read_text(encoding="utf-8")):
                date = datetime.strptime(e["date"], "%m/%d/%y").date().isoformat()
                entries.append({"date": date, "weight": round(e["weight"] * 0.453592, 1)})
        except Exception as ex:
            logger.warning(f"Failed to parse {path.name}: {ex}")

    seen = {}
    for e in entries:
        seen[e["date"]] = e["weight"]  # last entry per day wins
    return [{"date": d, "weight": seen[d]} for d in sorted(seen)]


def _load_steps_daily() -> list:
    """Per-minute step events summed into daily totals."""
    daily = defaultdict(float)
    for path in sorted(GLOBAL_EXPORT.glob("steps-*.json")):
        try:
            for e in json.loads(path.read_text(encoding="utf-8")):
                dt = datetime.strptime(e["dateTime"], "%m/%d/%y %H:%M:%S")
                daily[dt.date().isoformat()] += float(e["value"])
        except Exception as ex:
            logger.warning(f"Failed to parse {path.name}: {ex}")

    return [{"date": d, "steps": int(daily[d])} for d in sorted(daily)]


def _load_sleep_score() -> list:
    """Recent nightly sleep score + duration from the Sleep Score export."""
    path = DATA_DIR / "Sleep Score" / "sleep_score.csv"
    if not path.exists():
        return []

    entries = []
    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ts = row.get("timestamp", "")
                score = row.get("overall_score", "")
                deep = row.get("deep_sleep_in_minutes", "")
                if not ts or not score:
                    continue
                date = ts.split("T")[0]
                entries.append({
                    "date": date,
                    "score": int(score),
                    "deep_minutes": int(deep) if deep else None,
                })
    except Exception as ex:
        logger.warning(f"Failed to parse sleep_score.csv: {ex}")
        return []

    entries.sort(key=lambda e: e["date"])
    return entries


def _load_nutrition() -> dict:
    """Meal timing/frequency patterns from the food log.
    Note: Fitatu's Health Connect sync doesn't carry calorie/macro numbers,
    only food names, meal type, and timestamps."""
    path = DATA_DIR / "Physical Activity_GoogleData" / "nutrition_log.csv"
    if not path.exists():
        return {"meal_type_counts": {}, "hour_histogram": {}, "top_foods": [], "logs_per_day": []}

    # Note: "start time"/"end time" in this export are day-boundary markers
    # (every row reads 22:00:00Z-21:59:59Z, a fixed UTC offset for the local
    # day), not real per-meal clock times — so there's no actual time-of-day
    # to chart, only which calendar day and meal type each entry belongs to.
    meal_type_counts = Counter()
    food_counts = Counter()
    logs_per_day = defaultdict(int)

    try:
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                meal_type = (row.get("meal type") or "").strip()
                food_name = (row.get("food name") or "").strip()
                start = row.get("start time", "")
                if meal_type not in ("BREAKFAST", "LUNCH", "DINNER", "SNACK"):
                    continue
                meal_type_counts[meal_type] += 1
                if food_name:
                    food_counts[food_name] += 1
                if start:
                    try:
                        dt = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ")
                        logs_per_day[dt.date().isoformat()] += 1
                    except ValueError:
                        pass
    except Exception as ex:
        logger.warning(f"Failed to parse nutrition_log.csv: {ex}")
        return {"meal_type_counts": {}, "top_foods": [], "logs_per_day": []}

    return {
        "meal_type_counts": dict(meal_type_counts),
        "top_foods": food_counts.most_common(12),
        "logs_per_day": [{"date": d, "count": logs_per_day[d]} for d in sorted(logs_per_day)],
    }
