import unittest
import socket
from airpnp.config import Config
from airpnp.getnifs import NetworkInterface
from cStringIO import StringIO


def fake_network_interfaces():
    lo = NetworkInterface("lo", 1)
    lo.addresses[socket.AF_INET] = "127.0.0.1"
    eth0 = NetworkInterface("eth0", 2)
    eth0.addresses[socket.AF_INET] = "10.10.10.1"
    return [lo, eth0]


def fake_outip():
    return "10.10.10.1"


class TestConfig(unittest.TestCase):

    def rl(self, lines):
        lines.append(None)
        lines.reverse()
        def _rl():
            return lines.pop()
        return _rl

    def setUp(self):
        self.config = Config(fake_network_interfaces(), fake_outip())
    
    def test_config_option_default(self):
        self.assertEqual(1, self.config.loglevel())

    def test_read_config_option(self):
        self.config.load(StringIO("[airpnp]\nloglevel=4\n"))
        self.assertEqual(4, self.config.loglevel())

    def test_interface_ip_defaults_to_outip(self):
        self.assertEqual("10.10.10.1", self.config.interface_ip())

    def test_read_interface_ip_from_config(self):
        self.config.load(StringIO("[airpnp]\ninterface=127.0.0.1\n"))
        self.assertEqual("127.0.0.1", self.config.interface_ip())

    def test_read_interface_name_from_config(self):
        self.config.load(StringIO("[airpnp]\ninterface=lo\n"))
        self.assertEqual("127.0.0.1", self.config.interface_ip())

    def test_get_interface_name_from_config(self):
        self.config.load(StringIO("[airpnp]\ninterface=127.0.0.1\n"))
        self.assertEqual("lo", self.config.interface_name())

    def test_get_interface_index_from_config(self):
        self.config.load(StringIO("[airpnp]\ninterface=127.0.0.1\n"))
        self.assertEqual(1, self.config.interface_index())

    def test_interface_must_be_ip_or_name(self):
        fileobj = StringIO("[airpnp]\ninterface=xyz\n")
        self.assertRaises(ValueError, self.config.load, fileobj)

