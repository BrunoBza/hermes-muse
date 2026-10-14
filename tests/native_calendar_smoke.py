"""Registered native tool checks; called by native_smoke with temporary homes."""
import json
from datetime import datetime, timedelta


def run(entry, runtime):
    from cron.jobs import list_jobs
    before = list_jobs(include_disabled=True)
    checks_before = runtime.store.all('source_check')
    notices_before = runtime.store.all('notification')

    def action(name, data=None):
        from tool_client import transport
        result = json.loads(entry.handler(transport({'action': name, 'data': data or {}})))
        from tool_client import record
        record(name,result)
        assert result['ok'], result
        return result['result']

    query = action('calendar_window')
    assert query['source_resource'] == 'calendars:rolling-30d'
    assert action('calendar_window', {'mode': 'month'})['source_resource'] == 'calendars:natural-month'
    start = datetime.fromisoformat(query['start'])
    events = [{'id': 'fixture-day-' + str(day), 'title': 'Synthetic preparation ' + str(day),
               'start': (start + timedelta(days=day, hours=-2 if day == 30 else 0)).isoformat(),
               'end': (start + timedelta(days=day, hours=-1 if day == 30 else 1)).isoformat(),
               'all_day': False, 'recurring': False, 'preparation': {'reason': 'Synthetic booking lead time'}}
              for day in (8, 30)]

    def page(items):
        return {'status': 'checked', 'observed_at': query['observed_at'], 'items': items}

    source = {'source': {'connection': 'synthetic-apple', 'account': 'test-only', 'resource': query['source_resource']},
              'title': 'Synthetic Apple calendar',
              'inventory': {'pages': [page([{'id': 'work', 'title': 'Fixture work', 'timezone': 'UTC'}])]},
              'calendars': [{'resource_id': 'work', 'window': query, 'pages': [page(events)]}]}
    view = action('calendar_view', {'window': query, 'sources': [source], 'discovery_complete': True})
    assert view['complete'] and len(view['preparation_candidates']) == 2, view
    assert view['calendar_writes'] == 0
    assert view['availability'] == 'observed_busy_only'
    # Raw Apple PIM shape, explicitly device-display semantics, through native action.
    from datetime import timezone
    raw = []
    for event in events:
        lo, hi = datetime.fromisoformat(event['start']).astimezone(timezone.utc), datetime.fromisoformat(event['end']).astimezone(timezone.utc)
        raw.append({'id': 'shared-series-id', 'title': event['title'], 'calendarId': 'apple-fixture',
                    'calendar': 'Fixture Apple', 'startDate': lo.isoformat(), 'endDate': hi.isoformat(),
                    'localStart': lo.strftime('%Y-%m-%d %I:%M %p'), 'localEnd': hi.strftime('%Y-%m-%d %I:%M %p'),
                    'isAllDay': False, 'recurrence': [{'frequency': 'daily', 'interval': 1}]})
    apple = {'source': {'connection': 'synthetic-apple-pim', 'account': 'eventkit-local-store', 'resource': query['source_resource']},
             'title': 'Synthetic Apple PIM', 'receipt_format': 'apple-pim', 'device_timezone': {'timezone': 'UTC'},
             'inventory': {'pages': [page([{'id': 'apple-fixture', 'title': 'Fixture Apple'}])]},
             'calendars': [{'resource_id': 'apple-fixture', 'window': query, 'pages': [page(raw)]}]}
    observed = action('calendar_view', {'window': query, 'sources': [source, apple], 'discovery_complete': True})
    assert not observed['complete'] and len(observed['events']) == 4
    assert observed['coverage'][1]['source_check']['status'] == 'partial'
    assert observed['coverage'][1]['source_check']['checked_resources'] == ['apple-fixture']
    assert all('occurrence_id' not in row['event'] for row in observed['events'] if row['source_title'] == apple['title'])
    # Assembly itself neither checkpoints source reads nor creates notices/jobs.
    assert runtime.store.all('source_check') == checks_before
    assert runtime.store.all('notification') == notices_before
    assert list_jobs(include_disabled=True) == before
