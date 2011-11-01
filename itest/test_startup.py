import unittest
from base import *

class TestStartup(unittest.TestCase):

    def test_startup_welcome_message(self):
        with AirpnpProcess() as q:
            found, _ = read_until(q, ".*Airpnp started.*")
            self.assertTrue(found)

