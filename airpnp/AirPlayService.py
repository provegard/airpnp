# -*- coding: utf-8 -*-
#
# Copyright (c) 2010 Martin S. <opensuse@sukimashita.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the "Software"),
# to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense,
# and/or sell copies of the Software, and to permit persons to whom the
# Software is furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL 
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

import platform
import uuid
import aplog as log

from ZeroconfService import ZeroconfService
from plist import read_binary_plist
from config import config
from airplayserver import BaseResource, AirPlayServer

from twisted.application.service import MultiService
from twisted.application.internet import TCPServer
from twisted.web import server, resource, error
from httplib import HTTPMessage
from cStringIO import StringIO

__all__ = [
    "AirPlayService",
    "AirPlayOperations",
]

CT_BINARY_PLIST = 'application/x-apple-binary-plist'


class PlaybackInfoResource(BaseResource):

    def render_GET(self, request):
        content = '<?xml version="1.0" encoding="UTF-8"?>\
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\
<plist version="1.0">\
<dict>\
<key>duration</key>\
<real>%f</real>\
<key>position</key>\
<real>%f</real>\
<key>rate</key>\
<real>%f</real>\
<key>playbackBufferEmpty</key>\
<%s/>\
<key>playbackBufferFull</key>\
<false/>\
<key>playbackLikelyToKeepUp</key>\
<true/>\
<key>readyToPlay</key>\
<%s/>\
<key>loadedTimeRanges</key>\
<array>\
    <dict>\
        <key>duration</key>\
        <real>%f</real>\
        <key>start</key>\
        <real>0.000000</real>\
    </dict>\
</array>\
<key>seekableTimeRanges</key>\
<array>\
    <dict>\
        <key>duration</key>\
        <real>%f</real>\
        <key>start</key>\
        <real>0.000000</real>\
    </dict>\
</array>\
</dict>\
</plist>'
        d, p = self.ops.get_scrub()
        if (d+p == 0):
            playbackBufferEmpty = 'true'
            readyToPlay = 'false'
        else:
            playbackBufferEmpty = 'false'
            readyToPlay = 'true'

        content = content % (float(d), float(p), int(self.ops.is_playing()), playbackBufferEmpty, readyToPlay, float(d), float(d))
        request.setHeader("Content-Type", "text/x-apple-plist+xml")
        return content


class PlayResource(BaseResource):

    def render_POST(self, request):
        parsedbody = self.parse_body(request.getAllHeaders(),
                                     request.content.read())

        # position may not be given for streaming media
        position = parsedbody['Start-Position'] if \
                parsedbody.has_key('Start-Position') else 0.0
        self.ops.play(parsedbody['Content-Location'], float(position))
        return ""

    def parse_body(self, headers, body):
        ctype = headers.get('content-type')
        if ctype == CT_BINARY_PLIST:
            parsedbody = read_binary_plist(StringIO(body))
        else:
            parsedbody = HTTPMessage(StringIO(body))
        return parsedbody


class StopResource(BaseResource):

    def render_POST(self, request):
        self.ops.stop(request.getAllHeaders())
        return ""


class ScrubResource(BaseResource):

    def render_GET(self, request):
        d, p = self.ops.get_scrub()
        content = "duration: " + str(float(d))
        content += "\nposition: " + str(float(p))
        return content

    def render_POST(self, request):
        position = request.args['position'][0]
        self.ops.set_scrub(float(position))
        return ""


class ReverseResource(BaseResource):

    def render_POST(self, request):
        self.ops.reverse(request.getAllHeaders())
        request.setResponseCode(101)
        request.setHeader("Upgrade", "PTTH/1.0")
        request.setHeader("Connection", "Upgrade")
        return ""


class RateResource(BaseResource):

    def render_POST(self, request):
        value = request.args['value'][0]
        self.ops.rate(float(value))
        return ""


class PhotoResource(BaseResource):

    def render_PUT(self, request):
        self.ops.photo(request.content.read(), request.getHeader('X-Apple-Transition'))
        return ""


class ServerInfoResource(BaseResource):

    def __init__(self, ops, deviceid, features, model):
        BaseResource.__init__(self, ops)
        self.deviceid = deviceid
        self.features = features
        self.model = model

    def render_GET(self, request):
        content = '<?xml version="1.0" encoding="UTF-8"?>\
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\
<plist version="1.0">\
<dict>\
<key>deviceid</key>\
<string>%s</string>\
<key>features</key>\
<integer>%d</integer>\
<key>model</key>\
<string>%s</string>\
<key>protovers</key>\
<string>1.0</string>\
<key>srcvers</key>\
<string>101.10</string>\
</dict>\
</plist>'
        content = content % (self.deviceid, self.features, self.model)
        request.setHeader("Content-Type", "text/x-apple-plist+xml")
        return content


class SlideshowFeaturesResource(BaseResource):

    def render_GET(self, request):
        content = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
<key>themes</key>
<array>
<dict>
<key>key</key>
<string>UPnP</string>
<key>name</key>
<string>UPnP</string>
</dict>
</array>
</dict>
</plist>"""
        request.setHeader("Content-Type", "text/x-apple-plist+xml")
        return content


class AirPlayOperations(object):

    def get_scrub(self):
        return 0, 0

    def is_playing(self):
        return False

    def set_scrub(self, position):
        pass

    def play(self, location, position):
        pass

    def stop(self, info):
        pass

    def reverse(self, info):
        pass

    def photo(self, data, transition):
        pass

    def rate(self, speed):
        pass


class AirPlayService(MultiService):

    def __init__(self, ops, name=None, host="0.0.0.0", port=22555):
        MultiService.__init__(self)

        self.ops = ops

        macstr = "%012X" % uuid.getnode()
        self.deviceid = ''.join("%s:" % macstr[i:i+2] for i in range(0, len(macstr), 2))[:-1]
        # 0x77 instead of 0x07 in order to support AirPlay from ordinary apps;
        # also means that the body for play will be a binary plist.
        self.features = 0x77
        self.model = "AppleTV2,1"

        # create TCP server
        TCPServer(port, AirPlayServer(self.create_site()), 5).setServiceParent(self)

        # create avahi service
        if (name is None):
            name = "Airplay Service on " + platform.node()
        zconf = ZeroconfService(name, port=port, stype="_airplay._tcp", text=["deviceid=" + self.deviceid, "features=" + hex(self.features), "model=" + self.model])
        zconf.setServiceParent(self)

        # for logging
        self.name_ = name
        self.host = host
        self.port = port

    def create_site(self):
        root = error.NoResource()
        root.putChild("playback-info", PlaybackInfoResource(self.ops))
        root.putChild("play", PlayResource(self.ops))
        root.putChild("stop", StopResource(self.ops))
        root.putChild("scrub", ScrubResource(self.ops))
        root.putChild("reverse", ReverseResource(self.ops))
        root.putChild("rate", RateResource(self.ops))
        root.putChild("photo", PhotoResource(self.ops))
        root.putChild("slideshow-features", SlideshowFeaturesResource(self.ops))
        root.putChild("server-info", ServerInfoResource(self.ops, self.deviceid,
                                                        self.features,
                                                        self.model))
        return root

    def startService(self):
        MultiService.startService(self)
        log.msg(1, "AirPlayService '%s' is running at %s:%d" % (self.name_, self.host,
                                                                self.port))
    def stopService(self):
        log.msg(1, "AirPlayService '%s' was stopped" % (self.name_, ))
        return MultiService.stopService(self)
