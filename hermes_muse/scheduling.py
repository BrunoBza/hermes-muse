"""Conservative proof of the minimum spacing for newly created watches."""

import re


def slots(field, high):
    values = set()
    for term in field.split(","):
        match = re.fullmatch(r"(\*|\d+(?:-\d+)?)(?:/(\d+))?", term)
        if not match:
            raise ValueError("Cannot prove watch spacing; use every 30m")
        span, raw_step = match.groups()
        step = int(raw_step or 1)
        if step < 1:
            raise ValueError("Invalid cron step")
        if span == "*":
            start, end = 0, high
        elif "-" in span:
            start, end = map(int, span.split("-"))
        else:
            # croniter reads N/step as N..max by step, not the single value N.
            start = int(span)
            end = high if raw_step else start
        if not 0 <= start <= end <= high:
            raise ValueError("Invalid cron range")
        values.update(range(start, end + 1, step))
    return sorted(values)


def validate_watch(schedule):
    from cron.jobs import parse_schedule

    parsed = parse_schedule(schedule)
    if parsed["kind"] == "once":
        return parsed
    if parsed["kind"] == "interval":
        if parsed["minutes"] < 30:
            raise ValueError("New repeating watches require at least 30 minutes")
        return parsed
    fields = parsed["expr"].split()
    if len(fields) != 5:
        raise ValueError("Cannot prove complex cron spacing; use every 30m")
    # Ignoring calendar restrictions is conservative: it adds possible executions.
    # Reject advanced day syntax rather than accidentally interpreting seconds/year.
    if any(not re.fullmatch(r"[A-Za-z0-9*,/-]+", f) for f in fields[2:]):
        raise ValueError("Cannot prove cron spacing; use every 30m")
    times = sorted(
        h * 60 + m for h in slots(fields[1], 23) for m in slots(fields[0], 59)
    )
    if (
        not times
        or min(b - a for a, b in zip(times, times[1:] + [times[0] + 1440])) < 30
    ):
        raise ValueError(
            "Every possible repeating watch interval must be at least 30 minutes"
        )
    # Non-hour DST transitions can compress otherwise safe local-time intervals.
    from hermes_time import now

    zone = now().tzinfo
    if getattr(zone, "key", "UTC") not in {
        "UTC",
        "Etc/UTC",
        "Asia/Shanghai",
        "Asia/Tokyo",
        "Asia/Singapore",
        "Asia/Hong_Kong",
    }:
        raise ValueError("Timezone transitions cannot be proven safe; use every 30m")
    return parsed
