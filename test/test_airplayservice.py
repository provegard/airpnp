import unittest
import httplib
import plistlib
import os.path
from mock import Mock
from airpnp.AirPlayService import AirPlayService
from airpnp.airplayserver import IAirPlayServer
from cStringIO import StringIO
from twisted.web import http, server
from twisted.internet import defer
from twisted.test.proto_helpers import StringTransport
from zope.interface import implements


class IAirPlayServerMock(Mock):
    implements(IAirPlayServer)

    def __init__(self, *args, **kwargs):
        Mock.__init__(self, IAirPlayServer.names(), *args, **kwargs)


class TestAirPlayProtocol(unittest.TestCase):

    def setUp(self):
        self.apserver = IAirPlayServerMock()
        service = AirPlayService(self.apserver, "test")
        service.deviceid = "01:00:17:44:60:d2"
        self.apserver.features = 0x77
        self.proto = http.HTTPChannel()
        self.proto.requestFactory = server.Request
        self.proto.site = server.Site(service.create_site())
        self.proto.makeConnection(StringTransport())

    def test_playback_info_method_calls(self):
        self._send_playback_info((0.0, 0.0), False)

        self.assertTrue(self.apserver.get_scrub.called)
        self.assertTrue(self.apserver.is_playing.called)

    def test_playback_info_response_content_type(self):
        self._send_playback_info((0.0, 0.0), False)

        resp = self._get_response()
        self.assertEqual(resp.getheader("Content-Type"),
                         "text/x-apple-plist+xml")

    def test_playback_info_response_data_not_playing(self):
        self._send_playback_info((0.0, 0.0), False)

        resp = self._get_response()
        plist = plistlib.readPlist(resp)

        self.assertEqual(plist["duration"], 0.0)
        self.assertEqual(plist["position"], 0.0)
        self.assertEqual(plist["rate"], 0.0)
        self.assertEqual(plist["playbackBufferEmpty"], True)
        self.assertEqual(plist["readyToPlay"], False)
        self.assertEqual(plist["loadedTimeRanges"][0]["duration"], 0.0)
        self.assertEqual(plist["seekableTimeRanges"][0]["duration"], 0.0)

    def test_playback_info_response_data_playing(self):
        self._send_playback_info((20.0, 2.0), True)

        resp = self._get_response()
        plist = plistlib.readPlist(resp)

        self.assertEqual(plist["duration"], 20.0)
        self.assertEqual(plist["position"], 2.0)
        self.assertEqual(plist["rate"], 1.0)
        self.assertEqual(plist["playbackBufferEmpty"], False)
        self.assertEqual(plist["readyToPlay"], True)
        self.assertEqual(plist["loadedTimeRanges"][0]["duration"], 20.0)
        self.assertEqual(plist["seekableTimeRanges"][0]["duration"], 20.0)

    def test_stop_method_calls(self):
        data = "POST /stop HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self._send_data(data)

        self.assertTrue(self.apserver.stop.called)
        
    def test_get_scrub_method_calls(self):
        self.apserver.get_scrub.return_value = defer.succeed((0.0, 0.0))
        data = "GET /scrub HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self._send_data(data)

        self.assertTrue(self.apserver.get_scrub.called)

    def test_get_scrub_response_data(self):
        self.apserver.get_scrub.return_value = defer.succeed((0.0, 0.0))
        data = "GET /scrub HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self._send_data(data)

        resp = self._get_response()
        body = resp.read()
        self.assertEqual(body, "duration: 0.0\nposition: 0.0")

    def test_set_scrub_method_calls(self):
        data = "POST /scrub?position=1.0 HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self._send_data(data)

        self.apserver.set_scrub.assert_called_with(1.0)

    def test_rate_method_calls(self):
        data = "POST /rate?value=1.0 HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self._send_data(data)

        self.apserver.rate.assert_called_with(1.0)

    def test_server_info_content_type(self):
        data = "GET /server-info HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self._send_data(data)

        resp = self._get_response()
        self.assertEqual(resp.getheader("Content-Type"),
                         "text/x-apple-plist+xml")

    def test_server_info_response_data(self):
        data = "GET /server-info HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self._send_data(data)

        resp = self._get_response()
        plist = plistlib.readPlist(resp)

        self.assertEqual(plist["deviceid"], "01:00:17:44:60:d2")
        self.assertEqual(plist["features"], 0x77)
        self.assertEqual(plist["model"], "AppleTV2,1")

    def test_play_with_strings_method_calls(self):
        data = "POST /play HTTP/1.1\r\nHost: www.example.com\r\n" + \
                "Content-Length: 59\r\n\r\nStart-Position: 1.0\n" + \
                "Content-Location: http://localhost/test"
        self._send_data(data)

        self.apserver.play.assert_called_with("http://localhost/test", 1.0)

    def test_play_without_position_method_calls(self):
        data = "POST /play HTTP/1.1\r\nHost: www.example.com\r\n" + \
                "Content-Length: 39\r\n\r\n" + \
                "Content-Location: http://localhost/test"
        self._send_data(data)

        self.apserver.play.assert_called_with("http://localhost/test", 0.0)

    def test_play_with_binary_plist_method_calls(self):
        fn = os.path.join(os.path.dirname(__file__), "plist/airplay.bin")
        fd = open(fn, "rb")
        try:
            bindata = fd.read()
        finally:
            fd.close()

        data = "POST /play HTTP/1.1\r\nHost: www.example.com\r\n" + \
                "Content-Type: application/x-apple-binary-plist\r\n" + \
                "Content-Length: %d\r\n\r\n" % (len(bindata), )
        data += bindata
        self._send_data(data)

        self.assertTrue(self.apserver.play.called)
        # changed 1 -> 0 between mock 0.8.0beta1 and beta3
        args = self.apserver.play.call_args[0]
        self.assertTrue(args[0].startswith("http://"))
        self.assertEqual(args[1], 0.0005364880198612809)

    def _send_playback_info(self, get_scrub_response, is_playing_response):
        self.apserver.get_scrub.return_value = defer.succeed(get_scrub_response)
        self.apserver.is_playing.return_value = defer.succeed(is_playing_response)
        data = "GET /playback-info HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self._send_data(data)

    def _send_data(self, data):
        self.proto.dataReceived(data)

    def _get_response(self):
        resp = httplib.HTTPResponse(FakeSock(self.proto.transport.value()))
        resp.begin()
        return resp


class FakeSock(object):

    def __init__(self, data):
        self.data = data

    def makefile(self, mode, bufsize=0):
        return StringIO(self.data)
