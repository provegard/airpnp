import unittest
import urllib2
from airpnp.util import *
from airpnp.upnp import SoapMessage, SoapError
from cStringIO import StringIO


def nosleep(seconds):
    pass


class RaisingOpener:

    def __init__(self):
        self.calls = 0

    def open(self, req, data=None, timeout=0):
        self.calls += 1
        self.req = req
        raise urllib2.URLError('error')


class TestGetMaxAge(unittest.TestCase):

    def test_with_proper_header(self):
        headers = {'CACHE-CONTROL': 'max-age=10'}
        max_age = get_max_age(headers)

        self.assertEqual(max_age, 10)

    def test_with_spaces_around_eq(self):
        headers = {'CACHE-CONTROL': 'max-age = 10'}
        max_age = get_max_age(headers)

        self.assertEqual(max_age, 10)

    def test_with_missing_max_age(self):
        headers = {'CACHE-CONTROL': 'xyz=10'}
        max_age = get_max_age(headers)

        self.assertIsNone(max_age)

    def test_with_missing_header(self):
        headers = {'a': 'b'}
        max_age = get_max_age(headers)

        self.assertIsNone(max_age)

    def test_with_malformed_max_age(self):
        headers = {'CACHE-CONTROL': 'max-age='}
        max_age = get_max_age(headers)

        self.assertIsNone(max_age)


class TestSendSoapMessage(unittest.TestCase):

    def setUp(self):
        self.old_opener = urllib2._opener

    def tearDown(self):
        urllib2.install_opener(self.old_opener)

    def test_request_headers(self):
        o = RaisingOpener()
        urllib2.install_opener(o)

        msg = SoapMessage('urn:schemas-upnp-org:service:ConnectionManager:1', 'GetCurrentConnectionIDs')
        try:
            send_soap_message('http://www.dummy.com', msg)
        except:
            pass

        req = o.req
        self.assertEqual(req.get_header('Content-type'), 'text/xml; charset="utf-8"')
        self.assertEqual(req.get_header('User-agent'), 'OS/1.0 UPnP/1.0 airpnp/1.0')
        self.assertEqual(req.get_header('Soapaction'),
                         '"urn:schemas-upnp-org:service:ConnectionManager:1#GetCurrentConnectionIDs"')

    def test_soap_response(self):
        class Opener:
            def open(self, req, data=None, timeout=0):
                response = SoapMessage('urn:schemas-upnp-org:service:ConnectionManager:1',
                                       'GetCurrentConnectionIDsResponse')
                return StringIO(response.tostring())

        o = Opener()
        urllib2.install_opener(o)

        msg = SoapMessage('urn:schemas-upnp-org:service:ConnectionManager:1', 'GetCurrentConnectionIDs')
        response = send_soap_message('http://www.dummy.com', msg)

        self.assertEqual(response.__class__, SoapMessage)
        self.assertEqual(response.get_header(),
                         '"urn:schemas-upnp-org:service:ConnectionManager:1#GetCurrentConnectionIDsResponse"')

    def test_soap_error_on_500_response(self):
        class Opener:
            def open(self, req, data=None, timeout=0):
                response = SoapError(501, 'Action Failed')
                raise urllib2.HTTPError('http://www.dummy.com', 500, 
                                        'Internal Error', None, 
                                        StringIO(response.tostring()))

        o = Opener()
        urllib2.install_opener(o)

        msg = SoapMessage('urn:schemas-upnp-org:service:ConnectionManager:1', 'GetCurrentConnectionIDs')
        response = send_soap_message('http://www.dummy.com', msg)

        self.assertEqual(response.__class__, SoapError)
        self.assertEqual(response.code, '501')

    def test_url_error_is_reraised(self):
        class Opener:
            def open(self, req, data=None, timeout=0):
                raise urllib2.URLError('error')

        o = Opener()
        urllib2.install_opener(o)

        msg = SoapMessage('urn:schemas-upnp-org:service:ConnectionManager:1', 'GetCurrentConnectionIDs')
        self.assertRaises(urllib2.URLError, send_soap_message,
                          'http://www.dummy.com', msg)

    def test_http_error_is_reraised_if_not_405_or_500(self):
        class Opener:
            def open(self, req, data=None, timeout=0):
                raise urllib2.HTTPError('http://www.dummy.com', 404, 
                                        'Not Found', None, 
                                        StringIO('Not Found'))

        o = Opener()
        urllib2.install_opener(o)

        msg = SoapMessage('urn:schemas-upnp-org:service:ConnectionManager:1', 'GetCurrentConnectionIDs')
        self.assertRaises(urllib2.HTTPError, send_soap_message,
                          'http://www.dummy.com', msg)

    def test_fallback_to_mpost(self):
        class Opener:
            def open(self, req, data=None, timeout=0):
                if req.get_method() == 'POST':
                    raise urllib2.HTTPError('http://www.dummy.com', 405, 
                                            'Method Not Allowed', None, 
                                            StringIO('Method Not Allowed'))
                else:
                    e = urllib2.URLError('')
                    e.headers = req.headers
                    raise e

        o = Opener()
        urllib2.install_opener(o)

        msg = SoapMessage('urn:schemas-upnp-org:service:ConnectionManager:1', 'GetCurrentConnectionIDs')
        try:
            send_soap_message('http://www.dummy.com', msg)
        except urllib2.URLError, e:
            self.assertEqual(e.headers['Man'],
                             '"http://schemas.xmlsoap.org/soap/envelope/"; ns=01')
            self.assertEqual(e.headers['01-soapaction'],
                             '"urn:schemas-upnp-org:service:ConnectionManager:1#GetCurrentConnectionIDs"')


class TestFetchUrl(unittest.TestCase):

    def setUp(self):
        self.old_opener = urllib2._opener

    def tearDown(self):
        urllib2.install_opener(self.old_opener)

    def test_request_with_url(self):
        # Mock Opener
        class Opener:
            def open(self, req, data=None, timeout=0):
                self.req = req
                return None

        o = Opener()
        urllib2.install_opener(o)
        fetch_url('http://www.dummy.com')

        self.assertEqual(o.req.__class__, urllib2.Request)
        self.assertEqual(o.req.get_full_url(), 'http://www.dummy.com')

    def test_reraise_url_error(self):
        o = RaisingOpener()
        urllib2.install_opener(o)

        self.assertRaises(urllib2.URLError, fetch_url, 'http://www.dummy.com')


class TestHmsToSec(unittest.TestCase):

    def test_hour_conversion(self):
        sec = hms_to_sec('1:00:00')
        self.assertEqual(sec, 3600.0)

    def test_minute_conversion(self):
        sec = hms_to_sec('0:10:00')
        self.assertEqual(sec, 600.0)

    def test_second_conversion(self):
        sec = hms_to_sec('0:00:05')
        self.assertEqual(sec, 5.0)

    def test_with_fraction(self):
        sec = hms_to_sec('0:00:05.5')
        self.assertEqual(sec, 5.5)

    def test_with_div_fraction(self):
        sec = hms_to_sec('0:00:05.1/2')
        self.assertEqual(sec, 5.5)

    def test_with_plus_sign(self):
        sec = hms_to_sec('+1:01:01')
        self.assertEqual(sec, 3661.0)

    def test_with_minus_sign(self):
        sec = hms_to_sec('-1:01:01')
        self.assertEqual(sec, -3661.0)

    def test_without_hour_part(self):
        self.assertRaises(ValueError, hms_to_sec, '00:00')

    def test_with_empty_hour_part(self):
        self.assertRaises(ValueError, hms_to_sec, ':00:00')

    def test_with_too_short_minute_part(self):
        self.assertRaises(ValueError, hms_to_sec, '0:0:00')

    def test_with_too_short_second_part(self):
        self.assertRaises(ValueError, hms_to_sec, '0:00:0')

    def test_with_negative_minute(self):
        self.assertRaises(ValueError, hms_to_sec, '0:-1:00')

    def test_with_too_large_minute(self):
        self.assertRaises(ValueError, hms_to_sec, '0:60:00')

    def test_with_negative_second(self):
        self.assertRaises(ValueError, hms_to_sec, '0:00:-1')

    def test_with_too_large_second(self):
        self.assertRaises(ValueError, hms_to_sec, '0:00:60')

    def test_with_div_fraction_unsatisfied_inequality(self):
        self.assertRaises(ValueError, hms_to_sec, '0:00:05.5/5')


class TestSecToHms(unittest.TestCase):

    def test_seconds_only_without_fraction(self):
        hms = sec_to_hms(5)
        self.assertEqual(hms, '0:00:05')

    def test_seconds_with_fraction(self):
        hms = sec_to_hms(5.5)
        self.assertEqual(hms, '0:00:05.5')

    def test_minute_conversion(self):
        hms = sec_to_hms(65)
        self.assertEqual(hms, '0:01:05')

    def test_hour_conversion(self):
        hms = sec_to_hms(3600)
        self.assertEqual(hms, '1:00:00')

    def test_negative_seconds_conversion(self):
        hms = sec_to_hms(-3661.0)
        self.assertEqual(hms, '-1:01:01')


class TestSplitUsn(unittest.TestCase):

    def test_split_two_parts(self):
        usn = 'uuid:x::type'
        p1, p2 = split_usn(usn)

        self.assertEqual(p1, 'uuid:x')
        self.assertEqual(p2, 'type')

    def test_split_only_udn(self):
        usn = 'uuid:x'
        p1, p2 = split_usn(usn)

        self.assertEqual(p1, 'uuid:x')
        self.assertEqual(p2, '')
