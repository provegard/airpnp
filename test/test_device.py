import unittest
import mock
import airpnp.upnp as upnp
from airpnp.device import *
from xml.etree import ElementTree


class TestDevice(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        f = open('test/device_root.xml', 'r')
        elem = ElementTree.parse(f)
        self.device = Device(elem, 'http://www.base.com')

    def test_device_base_url(self):
        self.assertEqual(self.device.get_base_url(), "http://www.base.com")

    def test_device_attributes(self):
        device = self.device

        self.assertEqual(device.friendlyName, 'WDTVLIVE')
        self.assertEqual(device.deviceType,
                         'urn:schemas-upnp-org:device:MediaRenderer:1')
        self.assertEqual(device.manufacturer, 'Western Digital Corporation')
        self.assertEqual(device.modelName, 'WD TV HD Live')

    def test_tostring(self):
        self.assertEqual(str(self.device), "WDTVLIVE [UDN=uuid:67ff722f-0090-a976-17db-e9396986c234]")

    def test_error_on_unknown_attribute(self):
        device = self.device
        with self.assertRaises(NameError):
            device.modelBlob

    def test_service_count(self):
        device = self.device
        services = [s for s in device]

        self.assertEqual(len(services), 3)

    def test_getting_service_by_id(self):
        device = self.device
        service = device['urn:upnp-org:serviceId:AVTransport']

        self.assertEqual(service.__class__, Service)


class TestService(unittest.TestCase):

    def setUp(self):
        f = open('test/device_root.xml', 'r')
        elem = ElementTree.parse(f)
        self.device = Device(elem, 'http://www.base.com')

        self.soap_sender = mock.Mock()

        self.service = self.device['urn:upnp-org:serviceId:AVTransport']
        f = open('test/service_scpd.xml', 'r')
        elem = ElementTree.parse(f)
        self.service.initialize(elem, self.soap_sender)

    def test_service_attributes(self):
        service = self.service

        self.assertEqual(service.serviceType, 'urn:schemas-upnp-org:service:AVTransport:1')
        self.assertEqual(service.serviceId, 'urn:upnp-org:serviceId:AVTransport')

    def test_resolution_of_urls(self):
        service = self.service

        # URLs are resolved using the base URL
        self.assertEqual(service.SCPDURL, 'http://www.base.com/MediaRenderer_AVTransport/scpd.xml')
        self.assertEqual(service.controlURL, 'http://www.base.com/MediaRenderer_AVTransport/control')
        self.assertEqual(service.eventSubURL, 'http://www.base.com/MediaRenderer_AVTransport/event')

    def test_service_action_existence(self):
        self.assertTrue(hasattr(self.service, 'GetCurrentTransportActions'))

    def test_service_action_calls_soap_sender(self):
        self.service.GetCurrentTransportActions(InstanceID="0")
        self.assertTrue(self.soap_sender.called)

    def test_service_action_throws_for_missing_argument(self):
        self.assertRaises(KeyError, self.service.GetCurrentTransportActions)

    def test_service_action_soap_sender_args(self):
        self.service.GetCurrentTransportActions(InstanceID="0")
        args, _ = self.soap_sender.call_args

        self.assertEqual(args[0], self.device)
        self.assertEqual(args[1], self.service.controlURL)
        self.assertEqual(args[2].__class__, upnp.SoapMessage)


    #TODO: 
    # - async + deferred
    # - getting result
