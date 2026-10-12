"""Pure adaptation of Apple PIM EventKit receipts, without connector I/O.

Import calendar helpers lazily to avoid a circular module initialization.
"""
import copy
from datetime import datetime

LIMITATIONS = [
    "Apple PIM observed instances only: source timezone and original all-day dates unavailable; device dates are display dates",
    "Apple PIM original recurrence identity, moved/exception flags and cancellation history unavailable; no cross-read instance reconciliation",
    "Apple PIM account identity unavailable; account denotes the local EventKit store, not a provider account",
    "Apple PIM busy/transparency and attendance status unavailable; shown events do not establish availability or confirmed attendance",
]


def adapt(source):
    from .calendar import instant, required_text, resolve_zone
    result = copy.deepcopy(source)
    device = result['device_timezone']
    zone = resolve_zone(device)  # Explicit receipt from the connector host, never the profile by assumption.
    result['capability_gaps'] = list(LIMITATIONS)
    if device.get('timezone_kind', 'iana') == 'fixed':
        result['capability_gaps'].append('Apple PIM device timezone is a fixed offset; DST transitions unavailable')
    for page in result['inventory'].get('pages', []):
        for resource in page['items']:
            resource['display_timezone'] = copy.deepcopy(device)
    for read in result.get('calendars', []):
        for page in read.get('pages', []):
            normalized = []
            for raw in page['items']:
                try:
                    required_text(raw, 'id')
                    required_text(raw, 'title')
                    if raw['calendarId'] != read['resource_id']:
                        raise ValueError('Apple event calendarId differs from queried resource')
                    if type(raw['isAllDay']) is not bool:
                        raise ValueError('Apple isAllDay must be a boolean')
                    if 'recurrence' in raw and not isinstance(raw['recurrence'], list):
                        raise ValueError('Apple recurrence must be a list of rules')
                    start, end = instant(raw['startDate']), instant(raw['endDate'])
                    # localStart/localEnd are en_US_POSIX device display strings, minute precision.
                    for field, at in (('localStart', start), ('localEnd', end)):
                        local = datetime.strptime(raw[field], '%Y-%m-%d %I:%M %p')
                        if local != at.astimezone(zone).replace(tzinfo=None, second=0, microsecond=0):
                            raise ValueError('Apple local/UTC times disagree with explicit device timezone')
                    event = {'id': raw['id'], 'title': raw['title'],
                             'start': raw['startDate'], 'end': raw['endDate'],
                             'all_day': raw['isAllDay'], 'recurring': bool(raw.get('recurrence')),
                             'time_basis': 'apple-pim-observed',
                             'identity_basis': 'native-id-and-observed-interval',
                             'recurrence_identity': 'unavailable', 'status': 'observed',
                             'recurrence_basis': 'rule-present' if raw.get('recurrence') else 'not-reported',
                             'original': copy.deepcopy(raw)}
                    # Availability/attendance is not exposed: do not invent confirmed or busy.
                    event['busy'] = False
                    event['busy_basis'] = 'unavailable'
                    if 'preparation' in raw:
                        # Optional Muse judgment annotation, not an EventKit property.
                        event['preparation'] = copy.deepcopy(raw['preparation'])
                    if raw['isAllDay']:
                        event['display_all_day_dates'] = {
                            'start': start.astimezone(zone).date().isoformat(),
                            'end_exclusive': end.astimezone(zone).date().isoformat(),
                            'timezone': copy.deepcopy(device), 'basis': 'device-display'}
                    normalized.append(event)
                except (KeyError, TypeError, ValueError) as exc:
                    page['status'] = 'partial'
                    page['error'] = 'Invalid Apple observation: ' + str(exc)
            page['items'] = normalized
    return result
