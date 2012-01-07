import unittest
import os.path
import datetime
from airpnp.plist import *
from airpnp.plist import UTC
from cStringIO import StringIO


class TestReadBinary(unittest.TestCase):

    def test_invalid_signature(self):
        fd = StringIO("hello, world")
        self.assertRaises(PListFormatError, read_binary_plist, fd)

    def test_parsing_setProperty_plist(self):
        data = 'bplist00\xd1\x01\x02Uvalue\xd4\x03\x04\x05\x06\x07\x07\x07\x07YtimescaleUvalueUepochUflags\x10\x00\x08\x0b\x11\x1a$*06\x00\x00\x00\x00\x00\x00\x01\x01\x00\x00\x00\x00\x00\x00\x00\x08\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x008'
        fd = StringIO(data)
        content = read_binary_plist(fd)
        self.assertTrue('value' in content)


def test_read_plist():  # generator function
    yield check_plist, 'plist/true.bin', True
    yield check_plist, 'plist/false.bin', False
    yield check_plist, 'plist/int8.bin', 255
    yield check_plist, 'plist/int16.bin', 65535
    yield check_plist, 'plist/int32.bin', 4294967295
    yield check_plist, 'plist/int63.bin', 9223372036854775807
    yield check_plist, 'plist/intneg1.bin', -1
    yield check_plist, 'plist/float32.bin', 1.0e10
    yield check_plist, 'plist/float64.bin', 1.0e100
    yield check_plist, 'plist/date.bin', datetime.datetime(2011, 7, 23, 15, tzinfo=UTC())
    yield check_plist, 'plist/string.bin', "hello"
    yield check_plist, 'plist/longstring.bin', "hello there, world!"
    yield check_plist, 'plist/unicode.bin', u"non-ascii \u00e5\u00e4\u00f6"
    yield check_plist, 'plist/data.bin', "pleasure."
    yield check_plist, 'plist/array.bin', [1, 2, 3]
    yield check_plist, 'plist/set.bin', {1, 2, 3}
    yield check_plist, 'plist/airplay.bin', {"Content-Location":
                                             "http://v9.lscache4.googlevideo.com/videoplayback?id=3eac4bbd43c31217&itag=18&uaopt=no-save&el=related&client=ytapi-apple-iphone&devKey=AdW2Kh1KB1Jkhso4mAT4nHgO88HsQjpE1a8d1GxQnGDm&app=youtube_gdata&ip=0.0.0.0&ipbits=0&expire=1313568456&sparams=id,itag,uaopt,ip,ipbits,expire&signature=625BB56F7EF7AB65ED34C5D2B09539AA90B4F6B4.4227E5A20028E6F86621FAB7F15827A79E31C9EE&key=yta1",
                                             "Start-Position": 0.0005364880198612809}


def check_plist(fname, expected):
    fd = read_file(fname)
    obj = read_binary_plist(fd)
    assert obj == expected


def read_file(fname):
    with open(os.path.join(os.path.dirname(__file__),
                           fname), 'rb') as fd:
        s = fd.read()
        return StringIO(s)
