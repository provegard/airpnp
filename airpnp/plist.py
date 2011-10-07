# -*- coding: utf-8 -*-
# Copyright (c) 2011, Per Rovegård <per@rovegard.se>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
# 1. Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright
#    notice, this list of conditions and the following disclaimer in the
#    documentation and/or other materials provided with the distribution.
# 3. Neither the name of the authors nor the names of its contributors
#    may be used to endorse or promote products derived from this software
#    without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from struct import unpack
from datetime import datetime, tzinfo, timedelta

__all__ = [
    'read_binary_plist',
    'PListFormatError',
    'PListUnhandledError',
]

# From CFDate Reference: "Absolute time is measured in seconds relative to the
# absolute reference date of Jan 1 2001 00:00:00 GMT".
SECS_EPOCH_TO_2001 = 978307200

MARKER_NULL = 0X00
MARKER_FALSE = 0X08
MARKER_TRUE = 0X09
MARKER_FILL = 0X0F
MARKER_INT = 0X10
MARKER_REAL = 0X20
MARKER_DATE = 0X33
MARKER_DATA = 0X40
MARKER_ASCIISTRING = 0X50
MARKER_UNICODE16STRING = 0X60
MARKER_UID = 0X80
MARKER_ARRAY = 0XA0
MARKER_SET = 0XC0
MARKER_DICT = 0XD0


def read_binary_plist(fd):
    """Read an object from a binary plist.
    
    The binary plist format is described in CFBinaryPList.c at
    http://opensource.apple.com/source/CF/CF-550/CFBinaryPList.c. Only the top
    level object is returned.

    Raise a PListFormatError or a PListUnhandledError if the input data cannot
    be fully understood.

    Arguments:
    fd -- a file-like object that is seekable

    """
    r = BinaryPListReader(fd)
    return r.read()


class PListFormatError(Exception):
    """Represent a binary plist format error."""
    pass


class PListUnhandledError(Exception):
    """Represent a binary plist error due to an unhandled feature."""
    pass


class BinaryPListReader(object):

    def __init__(self, fd):
        self._fd = fd

    def read(self):
        fd = self._fd

        # start from the beginning to check the signature
        fd.seek(0, 0)
        buf = fd.read(7)
        
        # verify the signature; the first version digit is always 0
        if buf != "bplist0":
            raise PListFormatError("Invalid signature: %s" % (buf, ))

        # seek to and read the trailer (validation omitted for now)
        fd.seek(-32, 2)
        buf = fd.read(32)

        sortVersion, offsetIntSize, objectRefSize, numObjects, topObject, \
                offsetTableOffset = unpack(">5x3B3Q", buf)

        # read the object offsets
        self._offsets = []
        fd.seek(offsetTableOffset, 0)
        for i in range(0, numObjects):
            self._offsets.append(self._read_sized_int(offsetIntSize))

        # index of object to read
        self._index = topObject

        return self._read_objects(1)[0]

    def _read_objects(self, count):
        ret = []
        for i in range(0, count):
            self._fd.seek(self._offsets[self._index])
            self._index += 1
            ret.append(self._read_object())
        return ret

    def _read_object(self):
        filepos = self._fd.tell()
        marker = ord(self._fd.read(1))
        nb1 = marker & 0xf0
        nb2 = marker & 0x0f

        if nb1 == MARKER_NULL:
            if marker == MARKER_NULL:
                obj = None
            elif marker == MARKER_FALSE:
                obj = False
            elif marker == MARKER_TRUE:
                obj = True
            #TODO: Fill byte, skip over
        elif nb1 == MARKER_INT:
            count = 1 << nb2
            obj = self._read_sized_int(count)
        elif nb1 == MARKER_REAL:
            obj = self._read_sized_float(nb2)
        elif marker == MARKER_DATE: # marker!
            secs = self._read_sized_float(3)
            secs += SECS_EPOCH_TO_2001
            obj = datetime.fromtimestamp(secs, UTC())
        elif nb1 == MARKER_DATA or nb1 == MARKER_ASCIISTRING:
            count = self._read_count(nb2)
            obj = self._fd.read(count)
        elif nb1 == MARKER_UNICODE16STRING:
            count = self._read_count(nb2)
            data = self._fd.read(count * 2)
            chars = unpack(">%dH" % (count, ), data)
            s = u''
            for ch in chars:
                s += unichr(ch)
            obj = s
        elif nb1 == MARKER_UID:
            count = 1 + nb2
            obj = self._read_sized_int(count)
        elif nb1 == MARKER_ARRAY:
            count = self._read_count(nb2)
            obj = self._read_objects(count)
        elif nb1 == MARKER_SET:
            count = self._read_count(nb2)
            obj = set({})
            for o in self._read_objects(count):
                obj.add(o)
        elif nb1 == MARKER_DICT:
            count = self._read_count(nb2)
            keys = self._read_objects(count)
            values = self._read_objects(count)
            obj = {}
            for i in range(0, count):
                obj[keys[i]] = values[i]

        try:
            return obj
        except NameError:
            raise PListFormatError("Unknown marker at position %d: %d" %
                                   (filepos, marker))

    def _read_count(self, nb2):
        count = nb2
        if count == 0xf:
            count = self._read_object()
        return count

    def _read_sized_float(self, log2count):
        if log2count == 2:
            # 32 bits
            ret, = unpack(">f", self._fd.read(4))
        elif log2count == 3:
            # 64 bits
            ret, = unpack(">d", self._fd.read(8))
        else:
            raise PListUnhandledError("Unhandled real size: %d" %
                                      (1 << log2count, ))
        return ret

    def _read_sized_int(self, count):
        # in format version '00', 1, 2, and 4-byte integers have to be
        # interpreted as unsigned, whereas 8-byte integers are signed
        # (and 16-byte when available). negative 1, 2, 4-byte integers
        # are always emitted as 8 bytes in format '00'
        buf = self._fd.read(count)
        if count == 1:
            ret = ord(buf)
        elif count == 2:
            ret, = unpack(">H", buf)
        elif count == 4:
            ret, = unpack(">I", buf)
        elif count == 8:
            ret, = unpack(">q", buf)
        else:
            raise PListUnhandledError("Unhandled int size: %d" %
                                      (count, ))
        return ret


class UTC(tzinfo):
    def utcoffset(self, dt):
        return timedelta(0)
    def tzname(self, dt):
        return "UTC"
    def dst(self, dt):
        return timedelta(0)


# typedef struct {
#    uint8_t  _unused[5];
#    uint8_t  _sortVersion;
#    uint8_t  _offsetIntSize;
#    uint8_t  _objectRefSize;
#    uint64_t _numObjects;
#    uint64_t _topObject;
#    uint64_t _offsetTableOffset;
# } CFBinaryPlistTrailer;
