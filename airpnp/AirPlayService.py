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

from datetime import datetime
from urlparse import urlparse, parse_qsl
from ZeroconfService import ZeroconfService
from plist import read_binary_plist
from config import config

from twisted.internet.protocol import Protocol, Factory
from twisted.application.service import MultiService
from twisted.application.internet import TCPServer
from httplib import HTTPMessage
from cStringIO import StringIO

__all__ = [
    "AirPlayService",
    "AirPlayProtocolHandler"
]

CT_BINARY_PLIST = 'application/x-apple-binary-plist'


class Request(object):
    """Request class used by AirPlayProtocolBase."""

    # buffer for holding received data
    buffer = ""

    # header dictionary, parsed from data
    headers = None


class AirPlayProtocolBase(Protocol):

    request = None

    def connectionMade(self):
        log.msg(1, 'AirPlay connection from %r' % (self.transport.getPeer(), ))

    def dataReceived(self, data):
        if self.request is None:
            self.request = Request()

        r = self.request
        r.buffer += data

        if r.headers is None and r.buffer.find("\r\n\r\n") != -1:
            # decode the header
            # we split the message into HTTP headers and content body
            header, body = r.buffer.split("\r\n\r\n", 1)

            # separate the request line
            reqline, headers = header.split("\r\n", 1)

            # read request parameters
            r.type_, r.uri, version = reqline.split()

            # parse the HTTP headers
            r.headers = HTTPMessage(StringIO(headers))

            # parse any uri query parameters
            r.params = None
            if (r.uri.find('?')):
                url = urlparse(r.uri)
                if (url[4] is not ""):
                    r.params = dict(parse_qsl(url[4]))
                    r.uri = url[2]

            # find out the size of the body
            r.content_length = int(r.headers['Content-Length'])

            # reset the buffer to only contain the body part
            r.buffer = body

        if not r.headers is None and len(r.buffer) == r.content_length:
            r.body = r.buffer
            self.process_message(r)
            self.request = None

    def process_message(self, request):
        pass


class AirPlayProtocolHandler(AirPlayProtocolBase):

    def process_message(self, request):
        log.msg(3, "AirPlay request for %s with headers %r and body '%s'" %
                (request.uri, request.headers.items(), request.body))
        try:
            return self._process(request)
        except:
            log.err(None, "Failed to process AirPlay request")
            answer = self.create_request(503)
            return answer

    def _process(self, request):
        answer = ""
        service = self.factory.service

        # process the request and run the appropriate callback
        if (request.uri.find('/playback-info')>-1):
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
            d, p = service.get_scrub()
            if (d+p == 0):
                playbackBufferEmpty = 'true'
                readyToPlay = 'false'
            else:
                playbackBufferEmpty = 'false'
                readyToPlay = 'true'

            content = content % (float(d), float(p), int(service.is_playing()), playbackBufferEmpty, readyToPlay, float(d), float(d))
            answer = self.create_request(200, "Content-Type: text/x-apple-plist+xml", content)
        elif (request.uri.find('/play')>-1):
            parsedbody = self.parse_body(request.headers, request.body)

            # position may not be given for streaming media
            position = parsedbody['Start-Position'] if \
                    parsedbody.has_key('Start-Position') else 0.0
            service.play(parsedbody['Content-Location'], float(position))
            answer = self.create_request()
        elif (request.uri.find('/stop')>-1):
            service.stop(request.headers)
            answer = self.create_request()
        elif (request.uri.find('/scrub')>-1):
            if request.type_ == 'GET':
                d, p = service.get_scrub()
                content = "duration: " + str(float(d))
                content += "\nposition: " + str(float(p))
                answer = self.create_request(200, "", content)
            elif request.type_ == 'POST':
                service.set_scrub(float(request.params['position']))
                answer = self.create_request()
        elif (request.uri.find('/reverse')>-1):
            service.reverse(request.headers)
            answer = self.create_request(101)
        elif (request.type_ == 'POST' and request.uri.find('/rate')>-1):
            service.rate(float(request.params['value']))
            answer = self.create_request()
        elif (request.type_ == 'PUT' and request.uri.find('/photo')>-1):
            service.photo(request.body, request.headers['X-Apple-Transition'])
            answer = self.create_request()
        elif (request.uri.find('/slideshow-features')>-1):
            answer = self.create_request(404)
        elif (request.type_ == 'GET' and request.uri.find('/server-info')>-1):
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
            content = content % (service.deviceid, service.features, service.model)
            answer = self.create_request(200, "Content-Type: text/x-apple-plist+xml", content)
        else:
            log.msg(1, "ERROR: AirPlay - Unable to handle request \"%s\"" %
                    (request.uri))
            answer = self.create_request(404)

        if(answer is not ""):
            self.transport.write(answer)

    def get_datetime(self):
        today = datetime.now()
        datestr = today.strftime("%a, %d %b %Y %H:%M:%S")
        return datestr+" GMT"

    def create_request(self, status = 200, header = "", body = ""):
        clength = len(bytes(body))
        if (status == 200):
            answer = "HTTP/1.1 200 OK"
        elif (status == 404):
            answer = "HTTP/1.1 404 Not Found"
        elif (status == 503):
            answer = "HTTP/1.1 503 Service Unavailable"
        elif (status == 101):
            answer = "HTTP/1.1 101 Switching Protocols"
            answer += "\r\nUpgrade: PTTH/1.0"
            answer += "\r\nConnection: Upgrade"
        answer += "\r\nDate: " + self.get_datetime()
        answer += "\r\nContent-Length: " + str(clength)
        if (header != ""):
            answer += "\r\n" + header
        answer += "\r\n\r\n"
        answer += body
        return answer

    def parse_body(self, headers, body):
        ctype = headers.get('content-type')
        if ctype == CT_BINARY_PLIST:
            parsedbody = read_binary_plist(StringIO(body))
        else:
            parsedbody = HTTPMessage(StringIO(body))
        return parsedbody



class AirPlayFactory(Factory):

    protocol = AirPlayProtocolHandler

    def __init__(self, service):
        self.service = service
        self.noisy = config.loglevel() >= 3


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


class AirPlayService(MultiService, AirPlayOperations):

    def __init__(self, name=None, host="0.0.0.0", port=22555):
        MultiService.__init__(self)
        macstr = "%012X" % uuid.getnode()
        self.deviceid = ''.join("%s:" % macstr[i:i+2] for i in range(0, len(macstr), 2))[:-1]
        # 0x77 instead of 0x07 in order to support AirPlay from ordinary apps;
        # also means that the body for play will be a binary plist.
        self.features = 0x77
        self.model = "AppleTV2,1"

        # create TCP server
        TCPServer(port,  AirPlayFactory(self), 5).setServiceParent(self)

        # create avahi service
        if (name is None):
            name = "Airplay Service on " + platform.node()
        zconf = ZeroconfService(name, port=port, stype="_airplay._tcp", text=["deviceid=" + self.deviceid, "features=" + hex(self.features), "model=" + self.model])
        zconf.setServiceParent(self)

        # for logging
        self.name_ = name
        self.host = host
        self.port = port

    def startService(self):
        MultiService.startService(self)
        log.msg(1, "AirPlayService '%s' is running at %s:%d" % (self.name_, self.host,
                                                                self.port))
    def stopService(self):
        log.msg(1, "AirPlayService '%s' was stopped" % (self.name_, ))
        return MultiService.stopService(self)
