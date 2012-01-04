import unittest
import mock
from airpnp.bridge import AVControlPoint
from twisted.internet import defer


class TestAVControlPoint(unittest.TestCase):

    def setUp(self):
        self.avtransport = mock.Mock()
        self.connmgr = mock.Mock()
        def gsbyid(id):
            if id == 'urn:upnp-org:serviceId:AVTransport':
                return self.avtransport
            elif id == 'urn:upnp-org:serviceId:ConnectionManager':
                return self.connmgr
            else:
                raise ValueError("Unknown id: " + id)
        device = mock.MagicMock()
        device.__getitem__ = mock.Mock(side_effect=gsbyid)
        self.avcp = AVControlPoint(device, None, "127.0.0.1")

        # mock away instance ID business since these methods check for 
        # attributes that will be auto-added by the mock service.
        self.avcp.allocate_instance_id = mock.Mock(return_value="0")
        self.avcp.release_instance_id = mock.Mock()

        # suppress logging
        self.avcp.msg = lambda *args: None

    def test_get_scrub_without_uri(self):
        # Deferred.result
        duration, position = self.avcp.get_scrub().result
        self.assertEqual(duration, 0.0)
        self.assertEqual(position, 0.0)

    def test_is_playing_without_uri(self):
        # Deferred.result
        playing = self.avcp.is_playing().result
        self.assertEqual(playing, False)

    def test_play_sets_uri_without_starting_to_play(self):
        self.avcp.set_session_id("123")
        self.avcp.play("http://www.example.com/video.avi", 0.1)

        self.avtransport.SetAVTransportURI.assert_called_with(
            InstanceID="0",
            CurrentURI="http://www.example.com/video.avi",
            CurrentURIMetaData="")
        self.assertFalse(self.avtransport.Play.called)

    def test_get_scrub_seeks_to_stored_play_position_if_duration_is_known(self):
        self.avcp.set_session_id("123")
        # to store position (pct)
        self.avcp.play("http://www.example.com/video.avi", 0.1)

        pos = {"TrackDuration": "0:01:40", "RelTime": "0:00:00"}
        self.avtransport.GetPositionInfo.return_value = defer.succeed(pos)

        self.avcp.get_scrub()

        self.avtransport.Seek.assert_called_with(
            InstanceID="0",
            Unit="REL_TIME",
            Target="0:00:10.000")

    def test_get_scrub_seeks_to_stored_play_position_if_duration_is_known_only_once(self):
        self.avcp.set_session_id("123")
        # to store position (pct)
        self.avcp.play("http://www.example.com/video.avi", 0.1)

        pos = {"TrackDuration": "0:01:40", "RelTime": "0:00:00"}
        self.avtransport.GetPositionInfo.return_value = defer.succeed(pos)

        self.avcp.get_scrub()
        self.avcp.get_scrub()

        self.assertEqual(1, self.avtransport.Seek.call_count)

    def test_get_scrub_doesnt_seek_to_stored_play_position_if_current_position_is_greater(self):
        self.avcp.set_session_id("123")
        # to store position (pct)
        self.avcp.play("http://www.example.com/video.avi", 0.1)

        pos = {"TrackDuration": "0:01:40", "RelTime": "0:00:11"}
        self.avtransport.GetPositionInfo.return_value = defer.succeed(pos)

        self.avcp.get_scrub()

        self.assertFalse(self.avtransport.Seek.called)

    def test_get_scrub_doesnt_seek_to_stored_play_position_if_duration_is_unknown(self):
        self.avcp.set_session_id("123")
        # to store position (pct)
        self.avcp.play("http://www.example.com/video.avi", 0.1)

        pos = {"TrackDuration": "0:00:00", "RelTime": "0:00:00"}
        self.avtransport.GetPositionInfo.return_value = defer.succeed(pos)

        self.avcp.get_scrub()

        self.assertFalse(self.avtransport.Seek.called)

    def test_set_scrub_doesnt_seek_without_uri(self):
        self.avcp.set_scrub(5.0)
        self.assertFalse(self.avtransport.Seek.called)

    def test_set_scrub_seeks_with_uri(self):
        self.avcp.set_session_id("123")
        self.avcp.play("http://www.example.com/video.avi", 0.1)

        self.avcp.set_scrub(5.0)
        self.avtransport.Seek.assert_called_with(InstanceID="0",
                                                 Unit="REL_TIME",
                                                 Target="0:00:05.000")

