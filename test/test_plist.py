import unittest
import os.path
import datetime
from airpnp.plist import *
from airpnp.plist import UTC
from cStringIO import StringIO


DATA = [
    ['plist/true.bin', True],
    ['plist/false.bin', False],
    ['plist/int8.bin', 255],
    ['plist/int16.bin', 65535],
    ['plist/int32.bin', 4294967295],
    ['plist/int63.bin', 9223372036854775807],
    ['plist/intneg1.bin', -1],
    ['plist/float32.bin', 1.0e10],
    ['plist/float64.bin', 1.0e100],
    ['plist/date.bin', datetime.datetime(2011, 7, 23, 15, tzinfo=UTC())],
    ['plist/string.bin', "hello"],
    ['plist/longstring.bin', "hello there, world!"],
    ['plist/unicode.bin', u"non-ascii \u00e5\u00e4\u00f6"],
    ['plist/data.bin', "pleasure."],
    ['plist/array.bin', [1, 2, 3]],
    ['plist/set.bin', {1, 2, 3}],
    ['plist/airplay.bin', {"Content-Location":
                           "http://v9.lscache4.googlevideo.com/videoplayback?id=3eac4bbd43c31217&itag=18&uaopt=no-save&el=related&client=ytapi-apple-iphone&devKey=AdW2Kh1KB1Jkhso4mAT4nHgO88HsQjpE1a8d1GxQnGDm&app=youtube_gdata&ip=0.0.0.0&ipbits=0&expire=1313568456&sparams=id,itag,uaopt,ip,ipbits,expire&signature=625BB56F7EF7AB65ED34C5D2B09539AA90B4F6B4.4227E5A20028E6F86621FAB7F15827A79E31C9EE&key=yta1",
                           "Start-Position": 0.0005364880198612809}]
]

class DataProvider(type):

    def __new__(meta, classname, bases, classDict):
        def create_test_method(fname, expected):
            def test_method(self):
                fd = self.read_file(fname)
                obj = read_binary_plist(fd)
                self.assertEqual(obj, expected)
            return test_method

        # replacement dictionary
        newClassDict = {}

        # add the old methods
        for attrName, attr in classDict.items():
            newClassDict[attrName] = attr

        # generate new method based on test data
        for fname, expected in DATA:
            part = os.path.splitext(os.path.basename(fname))[0]
            newClassDict["test_" + part] = create_test_method(fname, expected)

        # create!
        return type.__new__(meta, classname, bases, newClassDict)

class TestReadBinary(unittest.TestCase):

    __metaclass__ = DataProvider

    def test_invalid_signature(self):
        fd = StringIO("hello, world")
        self.assertRaises(PListFormatError, read_binary_plist, fd)

    def read_file(self, fname):
        fd = open(os.path.join(os.path.dirname(__file__),
                               fname), 'rb')
        try:
            s = fd.read()
            return StringIO(s)
        finally:
            fd.close()
