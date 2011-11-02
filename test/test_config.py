import unittest
import sys
import socket
from airpnp.config import *
from mock import patch
from cStringIO import StringIO


class TestConfig(unittest.TestCase):

    def rl(self, lines):
        lines.append(None)
        lines.reverse()
        def _rl():
            return lines.pop()
        return _rl

    def setUp(self):
        # clear the config
        config.__init__()
    
    def test_config_option_default(self):
        self.assertEqual(1, config.loglevel())

    def test_hostname_defaults_to_fqdn(self):
        self.assertEqual(socket.getfqdn(), config.hostname())

    @patch('__builtin__.open')
    def test_read_config_option(self, open_mock):
        open_mock.return_value.readline.side_effect = self.rl(["[airpnp]", "loglevel=4"])
        config.load(__file__)
        self.assertEqual(4, config.loglevel())

    @patch('__builtin__.open')
    def test_nonexistent_file_is_ignored_on_read(self, open_mock):
        open_mock.return_value.readline.side_effect = self.rl(["[airpnp]", "loglevel=4"])
        config.load("nosuchfile")
        self.assertEqual(1, config.loglevel())

    def test_interface_defaults_to_0000(self):
        self.assertEqual("0.0.0.0", config.interface())

    @patch('__builtin__.open')
    def test_read_interface_from_config(self, open_mock):
        open_mock.return_value.readline.side_effect = self.rl(["[airpnp]", "interface=127.0.0.1"])
        config.load(__file__)
        self.assertEqual("127.0.0.1", config.interface())

    @patch('__builtin__.open')
    def test_interface_must_be_ip_address(self, open_mock):
        open_mock.return_value.readline.side_effect = self.rl(["[airpnp]", "interface=xyzvv"])
        self.assertRaises(ValueError, config.load, __file__)

