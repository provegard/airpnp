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

from ZeroconfService import ZeroconfService
from plist import read_binary_plist
from airplayserver import BaseResource, IAirPlayServer

from twisted.python import log
from twisted.application.service import MultiService
from twisted.application.internet import TCPServer
from twisted.web import error, server
from twisted.internet import defer
from httplib import HTTPMessage
from cStringIO import StringIO

__all__ = [
    "AirPlayService",
]

CT_BINARY_PLIST = 'application/x-apple-binary-plist'
CT_TEXT_PLIST = 'text/x-apple-plist+xml'


class PlaybackInfoResource(BaseResource):

    def render_GET(self, request):
        d1 = self.apserver.get_scrub()
        d2 = self.apserver.is_playing()
        dl = defer.DeferredList([d1, d2], consumeErrors=True)
        dl.addCallback(self.late_render_get, request)
        return dl
    
    def late_render_get(self, value, request):
        d, p = value[0][1]
        playing = value[1][1]

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

        if (d + p == 0):
            playbackBufferEmpty = 'true'
            readyToPlay = 'false'
        else:
            playbackBufferEmpty = 'false'
            readyToPlay = 'true'

        content = content % (float(d), float(p), int(playing), playbackBufferEmpty, readyToPlay, float(d), float(d))
        request.setHeader("Content-Type", CT_TEXT_PLIST)
        return content


class PlayResource(BaseResource):

    def render_POST(self, request):
        parsedbody = self.parse_body(request.getAllHeaders(),
                                     request.content.read())

        # position may not be given for streaming media
        position = parsedbody['Start-Position'] if \
                parsedbody.has_key('Start-Position') else 0.0
        self.apserver.play(parsedbody['Content-Location'], float(position))
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
        self.apserver.stop()
        return ""


class ScrubResource(BaseResource):

    def render_GET(self, request):
        d = self.apserver.get_scrub()
        d.addCallback(self.late_render_get)
        return d
    
    def late_render_get(self, value):
        d, p = value
        content = "duration: " + str(float(d))
        content += "\nposition: " + str(float(p))
        return content

    def render_POST(self, request):
        position = request.args['position'][0]
        self.apserver.set_scrub(float(position))
        return ""


class ReverseResource(BaseResource):

    def render_POST(self, request):
        self.apserver.reverse(None) #TODO
        request.setResponseCode(101)
        request.setHeader("Upgrade", "PTTH/1.0")
        request.setHeader("Connection", "Upgrade")
        return ""


class RateResource(BaseResource):

    def render_POST(self, request):
        value = request.args['value'][0]
        self.apserver.rate(float(value))
        return ""


class PhotoResource(BaseResource):

    def render_PUT(self, request):
        self.apserver.photo(request.content.read(), request.getHeader('X-Apple-Transition'))
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
        request.setHeader("Content-Type", CT_TEXT_PLIST)
        return content


class SlideshowFeaturesResource(BaseResource):

    def render_GET(self, request):
        content = '<?xml version="1.0" encoding="UTF-8"?>\
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\
<plist version="1.0">\
<dict>\
<key>themes</key>\
<array>\
<dict>\
<key>key</key>\
<string>UPnP</string>\
<key>name</key>\
<string>UPnP</string>\
</dict>\
</array>\
</dict>\
</plist>'
        request.setHeader("Content-Type", CT_TEXT_PLIST)
        return content


class AirPlayService(MultiService):

    def __init__(self, apserver, name=None, host="0.0.0.0", port=22555, index=-1):
        MultiService.__init__(self)

        self.apserver = IAirPlayServer(apserver)

        macstr = "%012X" % uuid.getnode()
        self.deviceid = ''.join("%s:" % macstr[i:i+2] for i in range(0, len(macstr), 2))[:-1]
        # 0x77 instead of 0x07 in order to support AirPlay from ordinary apps;
        # also means that the body for play will be a binary plist.
        self.features = 0x77
        self.model = "AppleTV2,1"

        # create TCP server
        TCPServer(port, self.create_site(), 100, interface=host).setServiceParent(self)

        # create avahi service
        if (name is None):
            name = "Airplay Service on " + platform.node()
        zconf = ZeroconfService(name, port=port, stype="_airplay._tcp", 
                                text=["deviceid=" + self.deviceid, "features=" + hex(self.features), "model=" + self.model],
                                index=index)
        zconf.setServiceParent(self)

        # for logging
        self.name_ = name
        self.host = host
        self.port = port

    def create_site(self):
        root = error.NoResource()
        root.putChild("playback-info", PlaybackInfoResource(self.apserver))
        root.putChild("play", PlayResource(self.apserver))
        root.putChild("stop", StopResource(self.apserver))
        root.putChild("scrub", ScrubResource(self.apserver))
        root.putChild("reverse", ReverseResource(self.apserver))
        root.putChild("rate", RateResource(self.apserver))
        root.putChild("photo", PhotoResource(self.apserver))
        root.putChild("slideshow-features", SlideshowFeaturesResource(self.apserver))
        root.putChild("server-info", ServerInfoResource(self.apserver, self.deviceid,
                                                        self.features,
                                                        self.model))
        return server.Site(root)

    def startService(self):
        MultiService.startService(self)
        log.msg("AirPlayService '%s' is running at %s:%d" % (self.name_, self.host,
                                                             self.port))
    def stopService(self):
        log.msg("AirPlayService '%s' was stopped" % (self.name_, ))
        return MultiService.stopService(self)
