"""Public Apple PIM shape with invented fixtures, no private calendar data."""
import copy
import unittest
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
import test_calendar as fixtures
from hermes_muse.service import Companion
from test_companion import Host, prepare


class AppleCalendarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = prepare(self.temp.name)
        self.now = datetime(2026, 10, 12, 12, tzinfo=ZoneInfo('America/New_York'))
        self.host = Host()
        self.host.local_now = lambda timestamp: datetime.fromtimestamp(timestamp, self.now.tzinfo)
        self.service = Companion(self.store, self.host, lambda: self.now.timestamp())
        self.query = self.service.calendar_window({})

    def page(self, items):
        return {'status': 'checked', 'observed_at': self.now.isoformat(), 'items': items}

    def view(self, source):
        return self.service.calendar_view({'window': self.query, 'sources': [source], 'discovery_complete': True})

    def raw(self, **changes):
        return {'id': 'fixture-instance', 'title': 'Synthetic observance',
                'calendarId': 'fixture-calendar', 'calendar': 'Synthetic calendar',
                'isAllDay': True, 'startDate': '2026-10-19T16:00:00Z',
                'endDate': '2026-10-21T16:00:00Z',
                'localStart': '2026-10-20 12:00 AM', 'localEnd': '2026-10-22 12:00 AM', **changes}

    def source(self, events=None):
        return {'source': {'connection': 'apple-pim', 'account': 'eventkit-local-store',
                           'resource': self.query['source_resource']},
                'title': 'Apple synthetic', 'receipt_format': 'apple-pim',
                'device_timezone': {'timezone': 'Asia/Shanghai', 'timezone_kind': 'iana'},
                'inventory': {'pages': [self.page([{'id': 'fixture-calendar', 'title': 'Synthetic calendar',
                                                  'source': 'Synthetic source', 'type': 'caldav'}])]},
                'calendars': [{'resource_id': 'fixture-calendar', 'window': self.query,
                               'pages': [self.page([self.raw()] if events is None else events)]}]}

    def test_real_shape_display_dates_utc_and_provenance_without_invention(self):
        source = self.source(); before = copy.deepcopy(source)
        result = self.view(source)
        self.assertEqual(source, before)
        self.assertFalse(result['complete'])
        self.assertEqual(result['coverage'][0]['source_check']['status'], 'partial')
        self.assertEqual(result['coverage'][0]['source_check']['checked_resources'], ['fixture-calendar'])
        row = result['events'][0]
        self.assertEqual(row['event']['original'], self.raw())
        self.assertEqual(row['event']['start'], self.raw()['startDate'])
        self.assertNotIn('timezone', row['calendar'])
        self.assertNotIn('all_day_dates', row)
        self.assertEqual(row['display_all_day_dates']['start'], '2026-10-20')
        self.assertEqual(row['display_all_day_dates']['end_exclusive'], '2026-10-22')
        self.assertEqual(row['display_all_day_dates']['basis'], 'device-display')
        # Profile is New York, device is Shanghai: retain both representations explicitly.
        self.assertTrue(row['local_start'].startswith('2026-10-19'))
        self.assertTrue(any(day['events'] for day in result['days']))
        self.assertTrue(all(not day['busy'] for day in result['days']))
        self.assertEqual(row['event']['status'], 'observed')

    def test_shared_native_id_expanded_instances_and_moved_observations_stay_distinct(self):
        first = self.raw(recurrence=[{'frequency': 'daily', 'interval': 1}])
        second = self.raw(startDate='2026-10-22T16:00:00Z', endDate='2026-10-23T16:00:00Z',
                          localStart='2026-10-23 12:00 AM', localEnd='2026-10-24 12:00 AM',
                          recurrence=first['recurrence'])
        result = self.view(self.source([first, second, copy.deepcopy(first)]))
        self.assertEqual(len(result['events']), 2)
        self.assertEqual(result['events'][0]['copies'], ['fixture-instance', 'fixture-instance'])
        for row in result['events']:
            self.assertTrue(row['event']['recurring'])
            self.assertNotIn('occurrence_id', row['event'])
            self.assertEqual(row['event']['recurrence_identity'], 'unavailable')
        self.assertFalse(result['complete'])

    def test_bad_local_time_resource_and_offset_preserve_valid_neighbors(self):
        for invalid in (self.raw(localStart='2026-10-19 12:00 AM'), self.raw(calendarId='other'),
                        self.raw(startDate='2026-10-19T16:00:00'), self.raw(isAllDay='true'),
                        self.raw(endDate='2026-10-18T16:00:00Z', localEnd='2026-10-19 12:00 AM')):
            with self.subTest(invalid=invalid):
                result = self.view(self.source([self.raw(), invalid]))
                self.assertEqual(len(result['events']), 1)
                self.assertFalse(result['coverage'][0]['source_check']['checked_resources'])
                self.assertFalse(result['complete'])

    def test_device_zone_required_and_dst_receipts_verified(self):
        source = self.source(); del source['device_timezone']
        with self.assertRaises(KeyError): self.view(source)
        source = self.source(); source['device_timezone'] = {'timezone': 'CST'}
        with self.assertRaises(KeyError): self.view(source)
        source = self.source(); source['device_timezone'] = {'timezone': 'CST', 'timezone_kind': 'fixed', 'utc_offset_seconds': 28800}
        self.assertIn('fixed offset', ' '.join(self.view(source)['gaps']))
        source = self.source([self.raw(startDate='2026-11-01T05:30:00Z', endDate='2026-11-01T06:30:00Z',
                           localStart='2026-11-01 1:30 AM', localEnd='2026-11-01 1:30 AM', isAllDay=False)])
        source['device_timezone'] = {'timezone': 'America/New_York'}
        result = self.view(source)
        self.assertEqual(len(result['events']), 1)
        self.assertNotEqual(result['events'][0]['local_start'], result['events'][0]['local_end'])

    def test_partial_page_and_limit_receipt_not_upgraded(self):
        source = self.source(); page = source['calendars'][0]['pages'][0]
        page.update(status='partial', error='limit reached without continuation')
        result = self.view(source)
        self.assertEqual(len(result['events']), 1)
        self.assertFalse(result['coverage'][0]['source_check']['checked_resources'])
        empty = self.view(self.source([]))
        self.assertFalse(empty['complete'])
        self.assertEqual(empty['events'], [])

    def test_no_persistence_and_partial_does_not_advance_last_success(self):
        result = self.view(self.source())
        self.assertFalse(self.store.all('source_check'))
        self.assertFalse(self.store.all('notification'))
        self.assertFalse(self.host.jobs)
        check = self.service.source_check(result['coverage'][0]['source_check'])
        self.assertFalse(check.get('last_success'))
        self.assertEqual(result['calendar_writes'], 0)
        fixture = fixtures.CalendarTests()
        fixture.query, fixture.now = self.query, self.now
        strict = fixture.source(connection='apple-pim', account='eventkit-local-store')
        baseline = self.service.source_check(self.view(strict)['coverage'][0]['source_check'])
        partial = self.service.source_check(result['coverage'][0]['source_check'])
        self.assertEqual(partial['last_success'], baseline['last_success'])
        self.assertEqual(partial['last_success_resources'], baseline['last_success_resources'])

    def test_supported_preparation_annotation_without_automatic_alert(self):
        result = self.view(self.source([self.raw(preparation={'reason': 'Synthetic travel booking evidence'})]))
        self.assertEqual(result['preparation_candidates'], [0])
        self.assertFalse(self.store.all('notification'))
        bad = self.view(self.source([self.raw(preparation={'due': '2026-10-13'})]))
        self.assertFalse(bad['events'])

    def test_strict_contract_cannot_opt_out_with_observed_marker(self):
        fixture = fixtures.CalendarTests()
        fixture.query = self.query
        fixture.now = self.now
        source = fixture.source([fixture.event(recurring=True,
                    time_basis='apple-pim-observed', status='observed')])
        source['inventory']['pages'][0]['items'][0]['display_timezone'] = {'timezone': 'UTC'}
        result = self.view(source)
        self.assertFalse(result['complete'])
        self.assertFalse(result['events'])


if __name__ == '__main__':
    unittest.main()
