# coding: utf-8
import datetime

from django.contrib.auth.models import Group
from django.http import Http404
from django.test import RequestFactory

import requests_mock

from workshops.tests.base import TestBase
from workshops.models import (
    Organization,
    Event,
    Role,
    Person,
    Task,
    Badge,
    Award,
    WorkshopRequest,
    Language,
)
from workshops.util import (
    fetch_event_metadata,
    generate_url_to_event_index,
    find_metadata_on_event_homepage,
    find_metadata_on_event_website,
    parse_metadata_from_event_website,
    validate_metadata_from_event_website,
    get_members,
    default_membership_cutoff,
    assignment_selection,
    create_username,
    InternalError,
    Paginator,
    assign,
    str2bool,
    human_daterange,
    match_notification_email,
)


class TestHandlingEventMetadata(TestBase):
    maxDiff = None

    html_content = """
<html><head>
<meta name="slug" content="2015-07-13-test" />
<meta name="startdate" content="2015-07-13" />
<meta name="enddate" content="2015-07-14" />
<meta name="country" content="us" />
<meta name="venue" content="Euphoric State University" />
<meta name="address" content="Highway to Heaven 42, Academipolis" />
<meta name="latlng" content="36.998977, -109.045173" />
<meta name="language" content="us" />
<meta name="invalid" content="invalid" />
<meta name="instructor" content="Hermione Granger|Ron Weasley" />
<meta name="helper" content="Peter Parker|Tony Stark|Natasha Romanova" />
<meta name="contact" content="hermione@granger.co.uk, rweasley@ministry.gov" />
<meta name="eventbrite" content="10000000" />
<meta name="charset" content="utf-8" />
</head>
<body>
<h1>test</h1>
</body></html>
"""
    yaml_content = """---
layout: workshop
root: .
venue: Euphoric State University
address: Highway to Heaven 42, Academipolis
country: us
language: us
latlng: 36.998977, -109.045173
humandate: Jul 13-14, 2015
humantime: 9:00 - 17:00
startdate: 2015-07-13
enddate: "2015-07-14"
instructor: ["Hermione Granger", "Ron Weasley",]
helper: ["Peter Parker", "Tony Stark", "Natasha Romanova",]
contact: hermione@granger.co.uk, rweasley@ministry.gov
etherpad:
eventbrite: 10000000
----
Other content.
"""

    @requests_mock.Mocker()
    def test_fetching_event_metadata_html(self, mock):
        "Ensure 'fetch_event_metadata' works correctly with HTML metadata provided."
        website_url = 'https://pbanaszkiewicz.github.io/workshop'
        repo_url = ('https://raw.githubusercontent.com/pbanaszkiewicz/'
                    'workshop/gh-pages/index.html')
        mock.get(website_url, text=self.html_content, status_code=200)
        mock.get(repo_url, text='', status_code=200)
        metadata = fetch_event_metadata(website_url)
        self.assertEqual(metadata['slug'], '2015-07-13-test')

    @requests_mock.Mocker()
    def test_fetching_event_metadata_yaml(self, mock):
        "Ensure 'fetch_event_metadata' works correctly with YAML metadata provided."
        website_url = 'https://pbanaszkiewicz.github.io/workshop'
        repo_url = ('https://raw.githubusercontent.com/pbanaszkiewicz/'
                    'workshop/gh-pages/index.html')
        mock.get(website_url, text='', status_code=200)
        mock.get(repo_url, text=self.yaml_content, status_code=200)
        metadata = fetch_event_metadata(website_url)
        self.assertEqual(metadata['slug'], 'workshop')

    def test_generating_url_to_index(self):
        tests = [
            'http://swcarpentry.github.io/workshop-template',
            'https://swcarpentry.github.com/workshop-template',
            'http://swcarpentry.github.com/workshop-template/',
            'http://github.com/swcarpentry/workshop-template',
            'https://github.com/swcarpentry/workshop-template',
        ]
        expected_url = ('https://raw.githubusercontent.com/swcarpentry/'
                        'workshop-template/gh-pages/index.html')
        expected_repo = 'workshop-template'
        for url in tests:
            with self.subTest(url=url):
                url, repo = generate_url_to_event_index(url)
                self.assertEqual(expected_url, url)
                self.assertEqual(expected_repo, repo)

    def test_finding_metadata_on_index(self):
        content = self.yaml_content
        expected = {
            'startdate': '2015-07-13',
            'enddate': '2015-07-14',
            'country': 'us',
            'venue': 'Euphoric State University',
            'address': 'Highway to Heaven 42, Academipolis',
            'latlng': '36.998977, -109.045173',
            'language': 'us',
            'instructor': 'Hermione Granger, Ron Weasley',
            'helper': 'Peter Parker, Tony Stark, Natasha Romanova',
            'contact': 'hermione@granger.co.uk, rweasley@ministry.gov',
            'eventbrite': '10000000',
        }
        self.assertEqual(expected, find_metadata_on_event_homepage(content))

    def test_finding_metadata_on_website(self):
        content = self.html_content
        expected = {
            'slug': '2015-07-13-test',
            'startdate': '2015-07-13',
            'enddate': '2015-07-14',
            'country': 'us',
            'venue': 'Euphoric State University',
            'address': 'Highway to Heaven 42, Academipolis',
            'latlng': '36.998977, -109.045173',
            'language': 'us',
            'instructor': 'Hermione Granger|Ron Weasley',
            'helper': 'Peter Parker|Tony Stark|Natasha Romanova',
            'contact': 'hermione@granger.co.uk, rweasley@ministry.gov',
            'eventbrite': '10000000',
        }

        self.assertEqual(expected, find_metadata_on_event_website(content))

    def test_parsing_empty_metadata(self):
        empty_dict = {}
        expected = {
            'slug': '',
            'language': '',
            'start': None,
            'end': None,
            'country': '',
            'venue': '',
            'address': '',
            'latitude': None,
            'longitude': None,
            'reg_key': None,
            'instructors': [],
            'helpers': [],
            'contact': '',
        }
        self.assertEqual(expected, parse_metadata_from_event_website(empty_dict))

    def test_parsing_correct_metadata(self):
        metadata = {
            'slug': '2015-07-13-test',
            'startdate': '2015-07-13',
            'enddate': '2015-07-14',
            'country': 'us',
            'venue': 'Euphoric State University',
            'address': 'Highway to Heaven 42, Academipolis',
            'latlng': '36.998977, -109.045173',
            'language': 'us',
            'instructor': 'Hermione Granger|Ron Weasley',
            'helper': 'Peter Parker|Tony Stark|Natasha Romanova',
            'contact': 'hermione@granger.co.uk, rweasley@ministry.gov',
            'eventbrite': '10000000',
        }
        expected = {
            'slug': '2015-07-13-test',
            'language': 'US',
            'start': datetime.date(2015, 7, 13),
            'end': datetime.date(2015, 7, 14),
            'country': 'US',
            'venue': 'Euphoric State University',
            'address': 'Highway to Heaven 42, Academipolis',
            'latitude': 36.998977,
            'longitude': -109.045173,
            'reg_key': 10000000,
            'instructors': ['Hermione Granger', 'Ron Weasley'],
            'helpers': ['Peter Parker', 'Tony Stark', 'Natasha Romanova'],
            'contact': 'hermione@granger.co.uk, rweasley@ministry.gov',
        }
        self.assertEqual(expected, parse_metadata_from_event_website(metadata))

    def test_parsing_tricky_country_language(self):
        """Ensure we always get a 2-char string or nothing."""
        tests = [
            (('Usa', 'English'), ('US', 'EN')),
            (('U', 'E'), ('', '')),
            (('', ''), ('', '')),
        ]
        expected = {
            'slug': '',
            'language': '',
            'start': None,
            'end': None,
            'country': '',
            'venue': '',
            'address': '',
            'latitude': None,
            'longitude': None,
            'reg_key': None,
            'instructors': [],
            'helpers': [],
            'contact': '',
        }

        for (country, language), (country_exp, language_exp) in tests:
            with self.subTest(iso_31661=(country, language)):
                metadata = dict(country=country, language=language)
                expected['country'] = country_exp
                expected['language'] = language_exp
                self.assertEqual(expected, parse_metadata_from_event_website(metadata))

    def test_parsing_tricky_dates(self):
        """Test if non-dates don't get parsed."""
        tests = [
            (('wrong start date', 'wrong end date'), (None, None)),
            (('11/19/2015', '11/19/2015'), (None, None)),
        ]
        expected = {
            'slug': '',
            'language': '',
            'start': None,
            'end': None,
            'country': '',
            'venue': '',
            'address': '',
            'latitude': None,
            'longitude': None,
            'reg_key': None,
            'instructors': [],
            'helpers': [],
            'contact': '',
        }

        for (startdate, enddate), (start, end) in tests:
            with self.subTest(dates=(startdate, enddate)):
                metadata = dict(startdate=startdate, enddate=enddate)
                expected['start'] = start
                expected['end'] = end
                self.assertEqual(expected, parse_metadata_from_event_website(metadata))

    def test_parsing_tricky_list_of_names(self):
        """Ensure we always get a list."""
        tests = [
            (('', ''), ([], [])),
            (('Hermione Granger', 'Peter Parker'),
             (['Hermione Granger'], ['Peter Parker'])),
            (('Harry,Ron', 'Hermione,Ginny'),
             (['Harry,Ron'], ['Hermione,Ginny'])),
            (('Harry| Ron', 'Hermione |Ginny'),
             (['Harry', 'Ron'], ['Hermione', 'Ginny'])),
        ]
        expected = {
            'slug': '',
            'language': '',
            'start': None,
            'end': None,
            'country': '',
            'venue': '',
            'address': '',
            'latitude': None,
            'longitude': None,
            'reg_key': None,
            'instructors': [],
            'helpers': [],
            'contact': '',
        }

        for (instructor, helper), (instructors, helpers) in tests:
            with self.subTest(people=(instructor, helper)):
                metadata = dict(instructor=instructor, helper=helper)
                expected['instructors'] = instructors
                expected['helpers'] = helpers
                self.assertEqual(expected, parse_metadata_from_event_website(metadata))

    def test_parsing_tricky_latitude_longitude(self):
        tests = [
            ('XYZ', (None, None)),
            ('XYZ, ', (None, None)),
            (',-123', (None, -123.0)),
            (',', (None, None)),
            (None, (None, None)),
        ]
        expected = {
            'slug': '',
            'language': '',
            'start': None,
            'end': None,
            'country': '',
            'venue': '',
            'address': '',
            'latitude': None,
            'longitude': None,
            'reg_key': None,
            'instructors': [],
            'helpers': [],
            'contact': '',
        }
        for latlng, (latitude, longitude) in tests:
            with self.subTest(latlng=latlng):
                metadata = dict(latlng=latlng)
                expected['latitude'] = latitude
                expected['longitude'] = longitude
                self.assertEqual(expected, parse_metadata_from_event_website(metadata))

    def test_parsing_tricky_eventbrite_id(self):
        tests = [
            ('', None),
            ('string', None),
            (None, None),
        ]
        expected = {
            'slug': '',
            'language': '',
            'start': None,
            'end': None,
            'country': '',
            'venue': '',
            'address': '',
            'latitude': None,
            'longitude': None,
            'reg_key': None,
            'instructors': [],
            'helpers': [],
            'contact': '',
        }
        for eventbrite_id, reg_key in tests:
            with self.subTest(eventbrite_id=eventbrite_id):
                metadata = dict(eventbrite=eventbrite_id)
                expected['reg_key'] = reg_key
                self.assertEqual(expected, parse_metadata_from_event_website(metadata))

    def test_validating_invalid_metadata(self):
        metadata = {
            'slug': 'WRONG FORMAT',
            'language': 'ENGLISH',
            'startdate': '07/13/2015',
            'enddate': '07/14/2015',
            'country': 'USA',
            'venue': 'Euphoric State University',
            'address': 'Highway to Heaven 42, Academipolis',
            'latlng': '3699e-4, -1.09e2',
            'instructor': 'Hermione Granger, Ron Weasley',
            'helper': 'Peter Parker, Tony Stark, Natasha Romanova',
            'contact': 'hermione@granger.co.uk, rweasley@ministry.gov',
            'eventbrite': 'bigmoney',
        }
        errors, warnings = validate_metadata_from_event_website(metadata)
        assert len(errors) == 7
        assert not warnings
        assert all([error.startswith('Invalid value') for error in errors])

    def test_validating_missing_metadata(self):
        metadata = {}
        errors, warnings = validate_metadata_from_event_website(metadata)
        assert len(errors) == 9  # There are nine required fields
        assert len(warnings) == 3  # There are three optional fields
        assert all([issue.startswith('Missing')
                    for issue in (errors + warnings)])

    def test_validating_empty_metadata(self):
        metadata = {
            'slug': '',
            'language': '',
            'startdate': '',
            'enddate': '',
            'country': '',
            'venue': '',
            'address': '',
            'latlng': '',
            'instructor': '',
            'helper': '',
            'contact': '',
            'eventbrite': '',
        }
        expected_errors = ['slug', 'startdate', 'country', 'latlng',
                           'instructor', 'helper', 'contact']
        errors, warnings = validate_metadata_from_event_website(metadata)
        assert not warnings
        for error, key in zip(errors, expected_errors):
            self.assertIn(key, error)

    def test_validating_default_metadata(self):
        metadata = {
            'slug': 'FIXME',
            'language': 'FIXME',
            'startdate': 'FIXME',
            'enddate': 'FIXME',
            'country': 'FIXME',
            'venue': 'FIXME',
            'address': 'FIXME',
            'latlng': 'FIXME',
            'eventbrite': 'FIXME',
            'instructor': 'FIXME',
            'helper': 'FIXME',
            'contact': 'FIXME',
        }
        errors, warnings = validate_metadata_from_event_website(metadata)
        assert len(errors) == 12
        assert not warnings
        assert all([
            error.startswith('Placeholder value "FIXME"')
            for error in errors
        ])

    def test_validating_correct_metadata(self):
        metadata = {
            'slug': '2015-07-13-test',
            'language': 'us',
            'startdate': '2015-07-13',
            'enddate': '2015-07-14',
            'country': 'us',
            'venue': 'Euphoric State University',
            'address': 'Highway to Heaven 42, Academipolis',
            'latlng': '36.998977, -109.045173',
            'eventbrite': '10000000',
            'instructor': 'Hermione Granger, Ron Weasley',
            'helper': 'Peter Parker, Tony Stark, Natasha Romanova',
            'contact': 'hermione@granger.co.uk, rweasley@ministry.gov',
        }
        errors, warnings = validate_metadata_from_event_website(metadata)
        assert not warnings
        assert not errors

    def test_no_attribute_error_missing_instructors_helpers(self):
        """Regression test: ensure no exception is raised when instructors
        or helpers aren't in the metadata or their values are None."""
        tests = [
            ((None, None), ([], [])),
            ((None, ''), ([], [])),
            (('', None), ([], [])),
        ]
        expected = {
            'slug': '',
            'language': '',
            'start': None,
            'end': None,
            'country': '',
            'venue': '',
            'address': '',
            'latitude': None,
            'longitude': None,
            'reg_key': None,
            'instructors': [],
            'helpers': [],
            'contact': '',
        }

        for (instructor, helper), (instructors, helpers) in tests:
            with self.subTest(people=(instructor, helper)):
                metadata = dict(instructor=instructor, helper=helper)
                expected['instructors'] = instructors
                expected['helpers'] = helpers
                self.assertEqual(expected, parse_metadata_from_event_website(metadata))


class TestMembership(TestBase):
    """Tests for SCF membership."""

    def setUp(self):
        super().setUp()
        self._setUpUsersAndLogin()

        one_day = datetime.timedelta(days=1)
        one_month = datetime.timedelta(days=30)
        three_years = datetime.timedelta(days=3 * 365)

        today = datetime.date.today()
        yesterday = today - one_day
        tomorrow = today + one_day

        # Set up events in the past, at present, and in future.
        past = Event.objects.create(
            host=self.org_alpha,
            slug="in-past",
            start=today - three_years,
            end=tomorrow - three_years
        )

        present = Event.objects.create(
            host=self.org_alpha,
            slug="at-present",
            start=today - one_month
        )

        future = Event.objects.create(
            host=self.org_alpha,
            slug="in-future",
            start=today + one_month,
            end=tomorrow + one_month
        )

        # Roles and badges.
        instructor_role = Role.objects.create(name='instructor')
        member_badge = Badge.objects.create(name='member')

        # Spiderman is an explicit member.
        Award.objects.create(person=self.spiderman, badge=member_badge,
                             awarded=yesterday)

        # Hermione teaches in the past, now, and in future, so she's a member.
        Task.objects.create(event=past, person=self.hermione,
                            role=instructor_role)
        Task.objects.create(event=present, person=self.hermione,
                            role=instructor_role)
        Task.objects.create(event=future, person=self.hermione,
                            role=instructor_role)

        # Ron only teaches in the distant past, so he's not a member.
        Task.objects.create(event=past, person=self.ron,
                            role=instructor_role)

        # Harry only teaches in the future, so he's not a member.
        Task.objects.create(event=future, person=self.harry,
                            role=instructor_role)

    def test_members_default_cutoffs(self):
        """Make sure default membership rules are obeyed."""
        earliest, latest = default_membership_cutoff()
        members = get_members(earliest=earliest, latest=latest)

        self.assertIn(self.hermione, members)  # taught recently
        self.assertNotIn(self.ron, members)  # taught too long ago
        self.assertNotIn(self.harry, members)  # only teaching in the future
        self.assertIn(self.spiderman, members)  # explicit member
        self.assertEqual(len(members), 2)

    def test_members_explicit_earliest(self):
        """Make sure membership rules are obeyed with explicit earliest
        date."""
        # Set start date to exclude Hermione.
        earliest = datetime.date.today() - datetime.timedelta(days=1)
        _, latest = default_membership_cutoff()
        members = get_members(earliest=earliest, latest=latest)

        self.assertNotIn(self.hermione, members)  # taught recently
        self.assertNotIn(self.ron, members)  # taught too long ago
        self.assertNotIn(self.harry, members)  # only teaching in the future
        self.assertIn(self.spiderman, members)  # explicit member
        self.assertEqual(len(members), 1)


class TestAssignmentSelection(TestBase):
    def setUp(self):
        """Set up RequestFactory and some users with different levels of
        privileges."""
        self.factory = RequestFactory()
        self.superuser = Person.objects.create_superuser(
            username='superuser', personal='admin', family='admin',
            email='superuser@superuser', password='superuser')
        self.admin = Person.objects.create_user(
            username='admin', personal='admin', family='admin',
            email='admin@admin', password='admin')
        self.admin.groups.set([Group.objects.get(name='administrators')])
        self.normal_user = Person.objects.create_user(
            username='user', personal='typical', family='user',
            email='typical@user', password='user')

    def test_no_selection_superuser(self):
        """User is superuser and they selected nothing. The result should be
        default value for this kind of a user."""
        request = self.factory.get('/')
        request.user = self.superuser
        assignment, is_admin = assignment_selection(request)
        self.assertEqual(assignment, 'all')
        self.assertFalse(is_admin)

    def test_no_selection_admin(self):
        """User is admin and they selected nothing. The result should be
        default value for this kind of a user."""
        request = self.factory.get('/')
        request.user = self.admin
        assignment, is_admin = assignment_selection(request)
        self.assertEqual(assignment, 'me')
        self.assertTrue(is_admin)

    def test_no_selection_normal_user(self):
        """User is normal user and they selected nothing. The result should be
        default value for this kind of a user."""
        request = self.factory.get('/')
        request.user = self.normal_user
        assignment, is_admin = assignment_selection(request)
        self.assertEqual(assignment, 'all')
        self.assertFalse(is_admin)

    def test_selection_normal_user(self):
        """User is normal user and they selected self-assigned. This is invalid
        selection (normal user cannot select anything), so the default option
        should be returned."""
        request = self.factory.get('/', {'assigned_to': 'me'})
        request.user = self.normal_user
        assignment, is_admin = assignment_selection(request)
        self.assertEqual(assignment, 'all')
        self.assertFalse(is_admin)

    def test_selection_privileged_user(self):
        """User is admin and they selected "not assigned to anyone". Actually
        for privileged user any selection should make through."""
        request = self.factory.get('/', {'assigned_to': 'noone'})
        request.user = self.admin
        assignment, is_admin = assignment_selection(request)
        self.assertEqual(assignment, 'noone')
        self.assertTrue(is_admin)


class TestUsernameGeneration(TestBase):
    def setUp(self):
        Person.objects.create_user(username='potter_harry', personal='Harry',
                                   family='Potter', email='hp@ministry.gov')

    def test_conflicting_name(self):
        """Ensure `create_username` works correctly when conflicting username
        already exists."""
        username = create_username(personal='Harry', family='Potter')
        self.assertEqual(username, 'potter_harry_2')

    def test_nonconflicting_name(self):
        """Ensure `create_username` works correctly when there's no conflicts
        in the database."""
        username = create_username(personal='Hermione', family='Granger')
        self.assertEqual(username, 'granger_hermione')

    def test_nonlatin_characters(self):
        """Ensure correct behavior for non-latin names."""
        username = create_username(personal='Grzegorz',
                                   family='Brzęczyszczykiewicz')
        self.assertEqual(username, 'brzczyszczykiewicz_grzegorz')

    def test_reached_number_of_tries(self):
        """Ensure we don't DoS ourselves."""
        tries = 1
        with self.assertRaises(InternalError):
            create_username(personal='Harry', family='Potter', tries=tries)

    def test_hyphenated_name(self):
        """Ensure people with hyphens in names have correct usernames
        generated."""
        username = create_username(personal='Andy', family='Blanking-Crush')
        self.assertEqual(username, 'blanking-crush_andy')


class TestPaginatorSections(TestBase):
    def make_paginator(self, num_pages, page_index=None):
        # there's no need to initialize with real values
        p = Paginator(object_list=None, per_page=1)
        p.num_pages = num_pages
        p._page_number = page_index
        return p

    def test_shortest(self):
        """Ensure paginator works correctly for only one page."""
        paginator = self.make_paginator(num_pages=1, page_index=1)
        sections = paginator.paginate_sections()
        self.assertEqual(list(sections), [1])

    def test_very_long(self):
        """Ensure paginator works correctly for big number of pages."""
        paginator = self.make_paginator(num_pages=20, page_index=1)
        sections = paginator.paginate_sections()
        self.assertEqual(
            list(sections),
            [1, 2, 3, 4, 5, None, 16, 17, 18, 19, 20]  # None is a break, '...'
        )

    def test_in_the_middle(self):
        """Ensure paginator puts two breaks when page index is in the middle
        of pages range."""
        paginator = self.make_paginator(num_pages=20, page_index=10)
        sections = paginator.paginate_sections()
        self.assertEqual(
            list(sections),
            # None is a break, it appears as '...' in the paginator widget
            [1, 2, 3, 4, 5, None, 8, 9, 10, 11, 12, 13, 14, None, 16, 17, 18,
             19, 20]
        )

    def test_at_the_end(self):
        """Ensure paginator puts one break when page index is in the right-most
        part of pages range."""
        paginator = self.make_paginator(num_pages=20, page_index=20)
        sections = paginator.paginate_sections()
        self.assertEqual(
            list(sections),
            # None is a break, it appears as '...' in the paginator widget
            [1, 2, 3, 4, 5, None, 16, 17, 18, 19, 20]
        )

    def test_long_no_breaks(self):
        """Ensure paginator doesn't add breaks when sections touch each
        other."""
        paginator = self.make_paginator(num_pages=17, page_index=8)
        sections = paginator.paginate_sections()
        self.assertEqual(
            list(sections),
            # None is a break, it appears as '...' in the paginator widget
            [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
        )


class TestAssignUtil(TestBase):
    def setUp(self):
        """Set up RequestFactory for making fast fake requests."""
        Person.objects.create_user(username='test_user', email='user@test',
                                   personal='User', family='Test')
        self.factory = RequestFactory()
        self.event = Event.objects.create(
            slug='event-for-assignment', host=Organization.objects.first())

    def test_no_integer_pk(self):
        """Ensure we fail with 404 when person PK is string, not integer."""
        tests = [
            (self.factory.get('/'), 'alpha'),
            (self.factory.post('/', {'person': 'alpha'}), None),
        ]
        for request, person_id in tests:
            with self.subTest(method=request.method):
                with self.assertRaises(Http404):
                    assign(request, self.event, person_id=person_id)

                # just reset the link, for safety sake
                self.event.assigned_to = None
                self.event.save()

    def test_assigning(self):
        """Ensure that with assignment is set correctly."""
        first_person = Person.objects.first()
        tests = [
            (self.factory.get('/'), first_person.pk),
            (self.factory.post('/', {'person': first_person.pk}), None),
        ]
        for request, person_id in tests:
            with self.subTest(method=request.method):
                # just reset the link, for safety sake
                self.event.assigned_to = None
                self.event.save()

                assign(request, self.event, person_id=person_id)
                self.event.refresh_from_db()
                self.assertEqual(self.event.assigned_to, first_person)

    def test_removing_assignment(self):
        """Ensure that with person_id=None, the assignment is removed."""
        first_person = Person.objects.first()
        tests = [
            (self.factory.get('/'), None),
            (self.factory.post('/'), None),
        ]
        for request, person_id in tests:
            with self.subTest(method=request.method):
                # just re-set the link to first person, for safety sake
                self.event.assigned_to = first_person
                self.event.save()

                assign(request, self.event, person_id=person_id)

                self.event.refresh_from_db()
                self.assertEqual(self.event.assigned_to, None)


class TestStr2Bool(TestBase):
    """Tests for ensuring str2bool works as expected."""
    def setUp(self):
        self.expected_true = (
            'True', 'TRUE', 'true', 'tRuE',
            '1',
            't', 'T',
            'yes', 'YES', 'yEs',
        )
        self.expected_false = (
            'False', 'FALSE', 'false', 'fAlSe',
            '0',
            'f', 'F',
            'no', 'NO', 'nO',
        )
        self.expected_none = (
            '',
            ' ',
            'dummy',
            'None',
            'asdgfh',
        )

    def test_true(self):
        """Ensure `True` is returned for correct input data."""
        for element in self.expected_true:
            self.assertEqual(str2bool(element), True, element)

    def test_false(self):
        """Ensure `False` is returned for correct input data."""
        for element in self.expected_false:
            self.assertEqual(str2bool(element), False, element)

    def test_none(self):
        """Ensure `None` is returned for correct input data."""
        for element in self.expected_none:
            self.assertIsNone(str2bool(element), element)


class TestHumanDaterange(TestBase):
    def setUp(self):
        self.formats = {
            'no_date': '????',
            'range_char': ' - ',
        }
        self.inputs = (
            (datetime.datetime(2018, 9, 1), datetime.datetime(2018, 9, 30)),
            (datetime.datetime(2018, 9, 30), datetime.datetime(2018, 9, 1)),
            (datetime.datetime(2018, 9, 1), datetime.datetime(2018, 12, 1)),
            (datetime.datetime(2018, 9, 1), datetime.datetime(2019, 12, 1)),
            (datetime.datetime(2018, 9, 1), None),
            (None, datetime.datetime(2018, 9, 1)),
            (None, None),
        )
        self.expected_outputs = (
            'Sep 01 - 30, 2018',
            'Sep 30 - 01, 2018',
            'Sep 01 - Dec 01, 2018',
            'Sep 01, 2018 - Dec 01, 2019',
            'Sep 01, 2018 - ????',
            '???? - Sep 01, 2018',
            '???? - ????',
        )

    def test_function(self):
        for i, v in enumerate(self.inputs):
            with self.subTest(i=i):
                left, right = v
                output = human_daterange(left, right, **self.formats)
                self.assertEqual(output, self.expected_outputs[i])


class TestMatchingNotificationEmail(TestBase):
    def setUp(self):
        self.request = WorkshopRequest.objects.create(
            state="p", personal="Harry", family="Potter", email="h@potter.com",
            institution_name="Hogwarts", location="Scotland", country="GB",
            part_of_conference=False, preferred_dates="soon",
            language=Language.objects.get(name='English'),
            audience_description="Students of Hogwarts",
            organization_type='self',
        )

    def test_default_criteria(self):
        # Online
        self.request.country = 'W3'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['team@carpentries.org'])

        # European Union
        self.request.country = 'EU'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['team@carpentries.org'])

        # United States
        self.request.country = 'US'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['team@carpentries.org'])

        # Poland
        self.request.country = 'PL'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['team@carpentries.org'])

        # unknown country code
        self.request.country = 'XY'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['team@carpentries.org'])

    def test_matching_Africa(self):
        """Testing just a subset of countries in Africa."""

        # the Democratic Republic of the Congo
        self.request.country = 'CD'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['admin-afr@carpentries.org'])

        # Nigeria
        self.request.country = 'NG'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['admin-afr@carpentries.org'])

        # South Sudan
        self.request.country = 'SS'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['admin-afr@carpentries.org'])

        # Somalia
        self.request.country = 'SO'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['admin-afr@carpentries.org'])

        # Egipt
        self.request.country = 'EG'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['admin-afr@carpentries.org'])

        # Tunisia
        self.request.country = 'TN'
        results = match_notification_email(self.request)
        self.assertEqual(results, ['admin-afr@carpentries.org'])

    def test_matching_UK_CA_NZ_AU(self):
        """Test a bunch of criteria automatically."""
        data = [
            ('GB', 'admin-uk@carpentries.org'),
            ('CA', 'admin-ca@carpentries.org'),
            ('NZ', 'admin-nz@carpentries.org'),
            ('AU', 'admin-au@carpentries.org'),
        ]
        for code, email in data:
            with self.subTest(code=code):
                self.request.country = code
                results = match_notification_email(self.request)
                self.assertEqual(results, [email])

    def test_object_no_criteria(self):
        self.assertFalse(hasattr(self, 'country'))
        results = match_notification_email(self)
        self.assertEqual(results, ['team@carpentries.org'])
