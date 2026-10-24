"""Deterministic windows/merge for long videos; no extra LLM or repair calls here."""

import json


def windows(duration, size=75):
    if not 60 <= size <= 90 or duration <= 0:
        raise ValueError("Window size must be 60–90 s and duration positive")
    return [
        (start, min(start + size, duration)) for start in range(0, __import__("math").ceil(duration), size)
    ]


def merge(parts):
    """Merge globally timed events and observations; reject contradictory duplicates."""
    merged = {}
    conflicts = []
    for part in parts:
        for section, items in part.items():
            if not isinstance(items, list):
                raise ValueError("Window sections must be lists")
            target = merged.setdefault(section, {})
            for item in items:
                key = item.get("id") or (item.get("kind"), item.get("start"), item.get("end"))
                encoded = json.dumps(item, sort_keys=True, ensure_ascii=False)
                if key in target and target[key][0] != encoded:
                    conflicts.append(
                        {"section": section, "key": str(key), "first": target[key][1], "second": item}
                    )
                else:
                    target[key] = (encoded, item)
    result = {
        k: sorted((v[1] for v in items.values()), key=lambda x: x.get("start", x.get("time", 0)))
        for k, items in merged.items()
    }
    return result, conflicts
