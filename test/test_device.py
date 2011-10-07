import unittest
from airpnp.device import *
from xml.etree import ElementTree


class TestDevice(unittest.TestCase):

    @classmethod
    def setUpClass(self):
        f = open('test/device_root.xml', 'r')
        elem = ElementTree.parse(f)
        self.device = Device(elem, 'http://www.base.com')

    def test_device_attributes(self):
        device = self.device

        self.assertEqual(device.friendlyName, 'WDTVLIVE')
        self.assertEqual(device.deviceType,
                         'urn:schemas-upnp-org:device:MediaRenderer:1')
        self.assertEqual(device.manufacturer, 'Western Digital Corporation')
        self.assertEqual(device.modelName, 'WD TV HD Live')

    def test_service_count(self):
        device = self.device
        services = device.get_services()

        self.assertEqual(len(services), 3)

    def test_getting_service_by_id(self):
        device = self.device
        service = device.get_service_by_id('urn:upnp-org:serviceId:AVTransport')

        self.assertEqual(service.__class__, Service)


class TestService(unittest.TestCase):

    def setUp(self):
        f = open('test/device_root.xml', 'r')
        elem = ElementTree.parse(f)
        self.device = Device(elem, 'http://www.base.com')

    def test_service_attributes(self):
        service = self.device.get_service_by_id('urn:upnp-org:serviceId:AVTransport')

        self.assertEqual(service.serviceType, 'urn:schemas-upnp-org:service:AVTransport:1')
        self.assertEqual(service.serviceId, 'urn:upnp-org:serviceId:AVTransport')

        # URLs are resolved using the base URL
        self.assertEqual(service.SCPDURL, 'http://www.base.com/MediaRenderer_AVTransport/scpd.xml')
        self.assertEqual(service.controlURL, 'http://www.base.com/MediaRenderer_AVTransport/control')
        self.assertEqual(service.eventSubURL, 'http://www.base.com/MediaRenderer_AVTransport/event')

    def test_service_actions(self):
        service = self.device.get_service_by_id('urn:upnp-org:serviceId:AVTransport')
        f = open('test/service_scpd.xml', 'r')
        elem = ElementTree.parse(f)
        service.initialize(elem, lambda url, msg: None)
        
        self.assertTrue(hasattr(service, 'GetCurrentTransportActions'))

    #TODO: 
    # - calling method
    # - not passing IN argument
    # - getting result
