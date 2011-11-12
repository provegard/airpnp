import unittest
import os
from mock import patch, Mock
from airpnp.device_builder import *
from twisted.internet import defer
from twisted.python import failure
from twisted.web import error, http

def readall(fn):
    with open(os.path.join(os.path.dirname(__file__), fn), 'r') as fd:
        return fd.read()

@patch('twisted.web.client.getPage')
class TestDeviceBuilder(unittest.TestCase):

    def test_build_device_returns_deferred(self, pageMock):
        pageMock.return_value = defer.Deferred()
        builder = DeviceBuilder(Mock())
        actual = builder.build('')

        self.assertEqual(actual.__class__, defer.Deferred)

    def test_build_device_error_with_dismissive_filter(self, pageMock):
        d = pageMock.return_value = defer.Deferred()
        builder = DeviceBuilder(Mock(), lambda x: (False, None))
        actual = builder.build('')
        err = [None]
        actual.addErrback(lambda x: err.__setitem__(0, x))
        d.callback(readall('ms.xml'))

        self.assertEqual(err[0].type, DeviceRejectedError)

    def test_build_device_error_with_missing_service(self, pageMock):
        def fetch(*args, **kw):
            def fetch2(*args, **kw):
                # second time: 404 Not Found
                return defer.fail(error.Error(http.NOT_FOUND, 'Not Found', 'Not Found'))
            pageMock.side_effect = fetch2
            # first time: return document
            return defer.succeed(readall('ms.xml'))
        pageMock.side_effect = fetch
        builder = DeviceBuilder(Mock(), lambda x: (True, None))
        actual = builder.build('')
        err = [None]
        actual.addErrback(lambda x: err.__setitem__(0, x))

        self.assertEqual(err[0].type, error.Error)

    def test_build_device_successfully(self, pageMock):
        def fetch(*args, **kw):
            def fetch2(*args, **kw):
                # second time: return service document
                return defer.succeed(readall('cds.xml'))
            pageMock.side_effect = fetch2
            # first time: return root document
            return defer.succeed(readall('ms.xml'))
        pageMock.side_effect = fetch
        builder = DeviceBuilder(Mock(), lambda x: (True, None))
        actual = builder.build('')

        # A pretty arbitrary assertion on the Device object
        self.assertEqual(actual.result.friendlyName, "pyupnp sample")

