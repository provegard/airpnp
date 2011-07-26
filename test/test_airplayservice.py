import unittest
import re
import httplib
import plistlib
import os.path
from mock import Mock
from airpnp.AirPlayService import *
from airpnp.AirPlayService import AirPlayProtocolBase, AirPlayOperations
from cStringIO import StringIO


class TestAirPlayProtocolBase(unittest.TestCase):

    MESSAGE = re.subn("\r?\n", "\r\n", """GET /path?param=value HTTP/1.1
Host: www.example.com
Content-Type: text/plain
Content-Length: 10

abcdefghij""")[0]
    PARTS = [MESSAGE[:55], MESSAGE[55:-10], MESSAGE[-10:-5], MESSAGE[-5:]]

    def setUp(self):
        self.handler = AirPlayProtocolBase()
        self.handler.process_message = Mock()

    def test_read_partial_header(self):
        self.handler.dataReceived(self.PARTS[0])
        self.assertFalse(self.handler.process_message.called)

    def test_read_whole_header(self):
        for part in self.PARTS[:2]:
            self.handler.dataReceived(part)
        self.assertFalse(self.handler.process_message.called)

    def test_read_header_and_part_body(self):
        for part in self.PARTS[:3]:
            self.handler.dataReceived(part)
        self.assertFalse(self.handler.process_message.called)

    def test_read_all_message_in_steps(self):
        for part in self.PARTS:
            self.handler.dataReceived(part)
        self.assertTrue(self.handler.process_message.called)

    def test_read_all_message_directly(self):
        self.handler.dataReceived(self.MESSAGE)
        self.assertTrue(self.handler.process_message.called)

    def test_request_data_when_reading_whole(self):
        self.handler.dataReceived(self.MESSAGE)

        r = self.handler.process_message.call_args[1][0]
        self._assert_request(r)

    def test_request_data_when_reading_in_steps(self):
        for part in self.PARTS:
            self.handler.dataReceived(part)

        r = self.handler.process_message.call_args[1][0]
        self._assert_request(r)

    def _assert_request(self, r):
        self.assertEqual(r.uri, "/path")
        self.assertEqual(r.params, {"param": "value"})
        self.assertEqual(r.body, "abcdefghij")
        self.assertEqual(r.headers.get("Content-Type"), "text/plain")


class TestAirPlayProtocol(unittest.TestCase):

    def setUp(self):
        self.ops = Mock(AirPlayOperations)
        self.ops.deviceid = "01:00:17:44:60:d2"
        self.ops.features = 0x77
        self.ops.model = "AModel"
        self.proto = AirPlayProtocolHandler()
        self.proto.factory = X()
        self.proto.factory.service = self.ops
        self.proto.transport = WritableString()

    def test_playback_info_method_calls(self):
        self._send_playback_info((0.0, 0.0), False)

        self.assertTrue(self.ops.get_scrub.called)
        self.assertTrue(self.ops.is_playing.called)

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
        self.proto.dataReceived(data)

        self.assertTrue(self.ops.stop.called)
        
    def test_get_scrub_method_calls(self):
        self.ops.get_scrub.return_value = 0.0, 0.0
        data = "GET /scrub HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self.proto.dataReceived(data)

        self.assertTrue(self.ops.get_scrub.called)

    def test_get_scrub_response_data(self):
        self.ops.get_scrub.return_value = 0.0, 0.0
        data = "GET /scrub HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self.proto.dataReceived(data)

        resp = self._get_response()
        body = resp.read()
        self.assertEqual(body, "duration: 0.0\nposition: 0.0")

    def test_set_scrub_method_calls(self):
        data = "POST /scrub?position=1.0 HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self.proto.dataReceived(data)

        self.ops.set_scrub.assert_called_with(1.0)

    def test_rate_method_calls(self):
        data = "POST /rate?value=1.0 HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self.proto.dataReceived(data)

        self.ops.rate.assert_called_with(1.0)

    def test_server_info_content_type(self):
        data = "GET /server-info HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self.proto.dataReceived(data)

        resp = self._get_response()
        self.assertEqual(resp.getheader("Content-Type"),
                         "text/x-apple-plist+xml")

    def test_server_info_response_data(self):
        data = "GET /server-info HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self.proto.dataReceived(data)

        resp = self._get_response()
        plist = plistlib.readPlist(resp)

        self.assertEqual(plist["deviceid"], self.ops.deviceid)
        self.assertEqual(plist["features"], self.ops.features)
        self.assertEqual(plist["model"], self.ops.model)

    def test_play_with_strings_method_calls(self):
        data = "POST /play HTTP/1.1\r\nHost: www.example.com\r\n" + \
                "Content-Length: 59\r\n\r\nStart-Position: 1.0\n" + \
                "Content-Location: http://localhost/test"
        self.proto.dataReceived(data)

        self.ops.play.assert_called_with("http://localhost/test", 1.0)

    def test_play_without_position_method_calls(self):
        data = "POST /play HTTP/1.1\r\nHost: www.example.com\r\n" + \
                "Content-Length: 39\r\n\r\n" + \
                "Content-Location: http://localhost/test"
        self.proto.dataReceived(data)

        self.ops.play.assert_called_with("http://localhost/test", 0.0)

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
        self.proto.dataReceived(data)

        self.assertTrue(self.ops.play.called)
        args = self.ops.play.call_args[1]
        self.assertTrue(args[0].startswith("http://"))
        self.assertEqual(args[1], 0.0005364880198612809)

    def _send_playback_info(self, get_scrub_response, is_playing_response):
        self.ops.get_scrub.return_value = get_scrub_response
        self.ops.is_playing.return_value = is_playing_response
        data = "GET /playback-info HTTP/1.1\r\nHost: www.example.com\r\nContent-Length: 0\r\n\r\n"
        self.proto.dataReceived(data)

    def _get_response(self):
        resp = httplib.HTTPResponse(FakeSock(self.proto.transport.written))
        resp.begin()
        return resp


class X(object):
    pass


class WritableString(object):

    def __init__(self):
        self.written = ""

    def write(self, data):
        self.written += data


class FakeSock(object):

    def __init__(self, data):
        self.data = data

    def makefile(self, mode, bufsize=0):
        return StringIO(self.data)
