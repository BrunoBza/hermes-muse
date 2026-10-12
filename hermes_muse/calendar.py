"""Stateless calendar assembly from authorized connector observations; no I/O."""
from __future__ import annotations

import copy
import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc


def resolve_zone(value):
    if value.get("timezone_kind", "iana") == "iana":
        return ZoneInfo(value["timezone"])
    if value["timezone_kind"] != "fixed":
        raise ValueError("timezone_kind must be iana or fixed")
    offset = value["utc_offset_seconds"]
    if type(offset) is not int or not -86400 < offset < 86400:
        raise ValueError("Fixed timezone requires an explicit offset under 24 hours")
    return timezone(timedelta(seconds=offset), value["timezone"])


def instant(value):
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timed dates need an explicit UTC offset")
    return result


def local_boundary(value, zone):
    # Resolve gaps forward and ambiguous boundaries to their first occurrence.
    return value.replace(tzinfo=zone, fold=0).astimezone(UTC).astimezone(zone)


def window(now, mode="rolling"):
    if now.tzinfo is None:
        raise ValueError("Profile time must be timezone-aware")
    if mode == "rolling":
        start = now
        end = local_boundary(now.replace(tzinfo=None) + timedelta(days=30), now.tzinfo)
    elif mode == "month":
        start = local_boundary(datetime(now.year, now.month, 1), now.tzinfo)
        year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
        end = local_boundary(datetime(year, month, 1), now.tzinfo)
    else:
        raise ValueError("mode must be rolling (future month/30 days) or month (this month)")
    result = {"mode": mode, "start": start.isoformat(), "end": end.isoformat(),
            "timezone": getattr(now.tzinfo, "key", str(now.tzinfo)), "bounds": "[start,end)",
            "source_resource": "calendars:rolling-30d" if mode == "rolling" else "calendars:natural-month",
            "observed_at": now.isoformat(), "days": 30 if mode == "rolling" else (end.date() - start.date()).days}
    result["timezone_kind"] = "iana" if getattr(now.tzinfo, "key", None) else "fixed"
    if result["timezone_kind"] == "fixed":
        result["utc_offset_seconds"] = int(now.utcoffset().total_seconds())
        result["timezone_note"] = "Fixed offset from active profile; DST transitions unavailable. Configure an IANA profile timezone for DST-aware boundaries."
    return result


def validate_window(value):
    zone = resolve_zone(value)
    observed = instant(value["observed_at"])
    expected = window(observed.astimezone(zone), value["mode"])
    if value != expected:
        raise ValueError("Use the unchanged calendar_window result for all calendar queries")
    return instant(value["start"]).astimezone(UTC), instant(value["end"]).astimezone(UTC), zone


def pages(value, observed, label, since):
    """Validate a full, ordered pagination chain, retaining earlier useful pages."""
    items, gaps, times = [], [], []
    if value.get("status", "checked") != "checked":
        gaps.append(label + ": " + value.get("status", "error") + ": " + str(value.get("error", "read failed")))
    token, seen = None, set()
    entries = value.get("pages", [])
    if not entries:
        gaps.append(label + ": no page receipt (empty requires a successful empty page)")
    for index, page in enumerate(entries):
        if page.get("request_token") != token or (index and token is None):
            gaps.append(label + ": broken pagination chain")
            break
        try:
            at = instant(page["observed_at"])
            if not since.timestamp() <= at.timestamp() <= observed.timestamp():
                raise ValueError("Page observation predates query or is in the future")
            if not isinstance(page["items"], list):
                raise ValueError("Page items must be a list")
        except (KeyError, TypeError, ValueError) as exc:
            gaps.append(label + ": " + str(exc))
            break
        times.append(at.isoformat())
        if page.get("status") != "checked":
            gaps.append(label + ": " + str(page.get("status", "error")) + ": " + str(page.get("error", "page failed")))
            if page.get("status") == "partial":
                items.extend(page["items"])
            break
        items.extend(page["items"])
        token = page.get("next_token")
        if token is not None:
            if not isinstance(token, str) or not token or token in seen:
                gaps.append(label + ": repeated/invalid continuation token")
                break
            seen.add(token)
    if token is not None:
        gaps.append(label + ": unread continuation page")
    return items, gaps, times


def required_text(value, field):
    result = value[field]
    if not isinstance(result, str) or not result.strip():
        raise ValueError(field + " must be nonempty text")
    return result


def event_times(event, resource):
    required_text(event, "id")
    required_text(event, "title")
    if type(event.get("all_day")) is not bool or type(event.get("recurring")) is not bool:
        raise ValueError("all_day and recurring must be explicit booleans")
    if "busy" in event and type(event["busy"]) is not bool:
        raise ValueError("busy must be a boolean")
    if event.get("preparation"):
        required_text(event["preparation"], "reason")
    observed = event.get("time_basis") == "apple-pim-observed"
    if observed and resource.get("display_timezone") is None:
        raise ValueError("Apple observations require explicit device display timezone")
    if event["recurring"] and not observed:
        required_text(event, "occurrence_id")  # Original RECURRENCE-ID, even for a moved exception.
    if event.get("rrule") and not event["recurring"]:
        raise ValueError("Expand recurring masters through the connector's instance query")
    if event.get("status", "confirmed") not in ({"observed"} if observed else {"confirmed", "tentative", "cancelled"}):
        raise ValueError("Unknown event status")
    if event["all_day"] and not observed:
        zone = resolve_zone(event if event.get("timezone") else resource)
        start = local_boundary(datetime.combine(date.fromisoformat(event["start"]), time()), zone)
        end = local_boundary(datetime.combine(date.fromisoformat(event["end"]), time()), zone)
    else:
        start, end = instant(event["start"]), instant(event["end"])
    if end.astimezone(UTC) <= start.astimezone(UTC):
        raise ValueError("Event end must be after start; all-day end is exclusive")
    return start.astimezone(UTC), end.astimezone(UTC)


def assemble(data, now):
    """Build schedules and proposed source_check arguments, never save event data."""
    query = data["window"]
    begin, end, zone = validate_window(query)
    since = instant(query["observed_at"])
    if since.timestamp() > now.timestamp():
        raise ValueError("Query snapshot cannot be in the future")
    sources = data["sources"]
    if not isinstance(sources, list):
        raise ValueError("sources must include every discovered authorized calendar connection/account")
    events, coverage, gaps = [], [], []
    identity_rows = {}
    seen_sources = set()
    for source in sources:
        if source.get("receipt_format") == "apple-pim":
            from .apple_calendar import adapt
            source = adapt(source)
        identity = source["source"]
        if set(identity) != {"connection", "account", "resource"}:
            raise ValueError("source requires stable connection/account/resource identity")
        for field in identity:
            required_text(identity, field)
        if identity["resource"] != query["source_resource"]:
            raise ValueError("Calendar windows need separate rolling-30d/natural-month source resources; preserve legacy checkpoints")
        source_key = tuple(identity[field] for field in sorted(identity))
        if source_key in seen_sources:
            raise ValueError("Supply one combined inventory per connection/account/resource")
        seen_sources.add(source_key)
        title = required_text(source, "title")
        resources, problems, inventory_times = pages(source["inventory"], now, title + " inventory", since)
        expected, checked, resource_rows = [], [], []
        for resource in resources:
            try:
                rid = required_text(resource, "id")
                required_text(resource, "title")
                if source.get("receipt_format") == "apple-pim":
                    resolve_zone(resource["display_timezone"])
                else:
                    required_text(resource, "timezone")
                    resolve_zone(resource)
                if rid in expected:
                    raise ValueError("Duplicate calendar inventory ID")
                expected.append(rid)
                resource_rows.append(resource)
            except (KeyError, TypeError, ValueError) as exc:
                problems.append(title + " inventory: " + str(exc))
        reads = source.get("calendars", [])
        if any(read.get("resource_id") not in expected for read in reads):
            problems.append(title + ": read of an unlisted resource")
        times = list(inventory_times)
        for resource in resource_rows:
            rid = resource["id"]
            matches = [read for read in reads if read.get("resource_id") == rid]
            if len(matches) != 1 or matches[0].get("window") != query:
                problems.append(title + "/" + rid + ": missing/duplicate read or different query interval")
                continue
            raw, failures, read_times = pages(matches[0], now, title + "/" + rid, since)
            times.extend(read_times)
            for event in raw:
                try:
                    if event.get("time_basis") == "apple-pim-observed" and source.get("receipt_format") != "apple-pim":
                        raise ValueError("Apple observed semantics require raw apple-pim receipts")
                    start, finish = event_times(event, resource)
                    occurrence = event.get("occurrence_id") if event["recurring"] else "single"
                    # Identity is scoped to the exact connection/account/calendar. Never fuzzy-match.
                    key = (identity["connection"], identity["account"], rid,
                           "uid:" + event["uid"] if event.get("uid") else "id:" + event["id"], occurrence)
                    if event.get("time_basis") == "apple-pim-observed":
                        # Observation-local key, never an original RECURRENCE-ID.
                        key = (identity["connection"], identity["account"], rid,
                               "id:" + event["id"], event["start"], event["end"])
                    row = {"source": copy.deepcopy(identity), "source_title": title,
                           "calendar": copy.deepcopy(resource), "event": copy.deepcopy(event),
                           "local_start": start.astimezone(zone).isoformat(), "local_end": finish.astimezone(zone).isoformat(),
                           "identity": list(key), "copies": [event["id"]]}
                    if event.get("display_all_day_dates"):
                        row["display_all_day_dates"] = copy.deepcopy(event["display_all_day_dates"])
                    if event["all_day"] and event.get("time_basis") != "apple-pim-observed":
                        row["all_day_dates"] = {"start": event["start"], "end_exclusive": event["end"],
                                                "timezone": event.get("timezone") or resource["timezone"]}
                    previous = identity_rows.get(key)
                    if previous is not None:
                        a, b = dict(events[previous]["event"]), dict(event)
                        a.pop("id"); b.pop("id")
                        if a == b:
                            events[previous]["copies"].append(event["id"])
                            continue
                        failures.append(title + "/" + rid + ": conflicting versions of the same occurrence; re-read original")
                    if finish > begin and start < end or event.get("status") == "cancelled":
                        identity_rows[key] = len(events)
                        events.append(row)
                except (KeyError, TypeError, ValueError) as exc:
                    failures.append(title + "/" + rid + ": invalid event: " + str(exc))
            if not failures:
                checked.append(rid)
            problems.extend(failures)
        # An actually queried empty inventory is a successful resource observation.
        if not expected and not problems:
            expected = checked = [identity["resource"] + ":inventory"]
        problems.extend(source.get("capability_gaps", []))
        status = "partial" if problems else "checked"
        if not resources and source["inventory"].get("status") in {"error", "unavailable"}:
            status = source["inventory"]["status"]
        check = {"source": copy.deepcopy(identity), "scope": json.dumps(query, sort_keys=True),
                 "started_at": query["observed_at"], "status": status,
                 "expected_resources": expected, "checked_resources": checked,
                 "summary": "; ".join(problems)[:2000] if problems else "Completed calendar inventory and all event pages",
                 "query_window": query, "observed_at": now.isoformat()}
        for field in ("source_id", "alias_reason", "cursor"):
            if field in source:
                check[field] = source[field]
        coverage.append({"source": identity, "title": title, "resources": resources,
                         "page_observations": times, "gaps": problems, "source_check": check})
        gaps.extend(problems)
    if data.get("discovery_complete") is not True:
        gaps.append("Connection/account discovery incomplete; other calendar sources may be missing")
    events.sort(key=lambda row: (instant(row["local_start"]).timestamp(), row["event"]["title"], row["event"]["id"]))
    days = []
    day = begin.astimezone(zone).date()
    while day < end.astimezone(zone).date() or local_boundary(datetime.combine(day, time()), zone).astimezone(UTC) < end:
        lo = max(begin, local_boundary(datetime.combine(day, time()), zone).astimezone(UTC))
        hi = min(end, local_boundary(datetime.combine(day + timedelta(days=1), time()), zone).astimezone(UTC))
        entries, busy = [], []
        for index, row in enumerate(events):
            event = row["event"]
            start, finish = instant(row["local_start"]).astimezone(UTC), instant(row["local_end"]).astimezone(UTC)
            if event.get("status") == "cancelled" or start >= hi or finish <= lo:
                continue
            entries.append(index)
            if event.get("busy", not event["all_day"]):
                busy.append((index, start, finish))
        overlaps = [[a[0], b[0]] for offset, a in enumerate(busy) for b in busy[offset + 1:]
                    if max(a[1], b[1], lo) < min(a[2], b[2], hi)]
        days.append({"date": day.isoformat(), "events": entries, "busy": [b[0] for b in busy], "overlaps": overlaps})
        day += timedelta(days=1)
    return {"window": query, "observed_at": now.isoformat(), "complete": not gaps,
            "gaps": gaps, "coverage": coverage, "events": events, "days": days,
            "preparation_candidates": [i for i, row in enumerate(events)
                                       if row["event"].get("preparation") and row["event"].get("status") != "cancelled"],
            "availability": "observed_busy_only", "calendar_writes": 0}
