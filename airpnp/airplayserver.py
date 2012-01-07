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

from twisted.web import resource, server
from twisted.internet import defer
from twisted.python import log
from zope.interface import Interface
from plist import read_binary_plist
from cStringIO import StringIO

__all__ = [
    'BaseResource',
    'IAirPlayServer',
    'SessionRejectedError',
    'SetPropertyResource',
    'CT_BINARY_PLIST',
    'CT_TEXT_PLIST',
]

CT_BINARY_PLIST = 'application/x-apple-binary-plist'
CT_TEXT_PLIST = 'text/x-apple-plist+xml'


class SessionRejectedError(Exception):
    pass


class IAirPlayServer(Interface):

    def set_session_id(sid):
        """Set the current session ID.

        Set the current session ID, as reported by the AirPlay client. If
        another session is already ongoing, raise a SessionRejectedError.

        """

    def get_scrub():
        """Return a tuple of (duration, position).

        Duration and position are measured in seconds:

        """

    def is_playing():
        """Return current playback status."""

    def set_scrub(position):
        """Seek to the given position (measured in seconds)."""

    def play(location, position):
        """Play the media at the given location.

        Location is the URI of the media to play. Position is the playback
        position as a percentage of the media duration.

        """

    def stop():
        """Stop playback."""

    def reverse(proxy):
        """TODO"""

    def photo(data, transition):
        """Show a photo.

        Data is the actual photo data, and transition is a transition to use
        when changing photo.

        """

    def rate(speed):
        """Adjust the playback speed."""

    def set_property(name, value):
        """Set the value of a property."""


class BaseResource(resource.Resource):

    def __init__(self, apserver):
        resource.Resource.__init__(self)
        self.apserver = IAirPlayServer(apserver)

    def render(self, request):
        log.msg("Got AirPlay request, URI = %s, %r"
                % (request.uri, request.requestHeaders), ll=3)
        sid = request.getHeader("X-Apple-Session-Id")
        ret = ""
        try:
            self.apserver.set_session_id(sid)
            ret = resource.Resource.render(self, request)
            if isinstance(ret, defer.Deferred):
                # get a Deferred for request notifications
                notify = request.notifyFinish()
                
                # wait for both Deferreds in parallel, but we want to know as
                # soon as one of them callbacks or errbacks
                dl = defer.DeferredList([ret, notify], fireOnOneCallback=True,
                                        fireOnOneErrback=True,
                                        consumeErrors=True)
                
                # add our handlers
                dl.addCallbacks(self.late_render, self.late_error,
                                callbackArgs=[request], errbackArgs=[request])
                
                # the request is not finished yet
                ret = server.NOT_DONE_YET
        except SessionRejectedError:
            request.setResponseCode(503)
        except:
            log.err(None, "Failed to process AirPlay request.")
            request.setResponseCode(501)
        return ret

    def late_render(self, result, request):
        # DeferredList callbacks with a two-tuple, the first value of which is
        # the result from the Deferred that fired. The notifyFinish Deferred
        # callbacks with value None when the request is finished normally.
        data = result[0]
        if data:
            try:
                # must set content-length to avoid chunked encoding
                request.setHeader('content-length', len(data))
                request.write(data)
                request.finish()
            except:
                log.err(None, "Failed to write response data for AirPlay request.")

    def late_error(self, fail, request):
        # DeferredList errbacks with a FirstError failure, from which we can
        # get the real failure.
        if isinstance(fail, defer.FirstError):
            fail = fail.subFailure
        log.err(fail, "AirPlay request handling failed.")
        if not request._disconnected:
            try:
                # must set content-length to avoid chunked encoding
                request.setHeader('content-length', 0)
                request.setResponseCode(501)
                request.finish()
            except:
                log.err(None, "Failed to write error response for AirPlay request.")


class SetPropertyResource(BaseResource):

    def render_PUT(self, request):
        ctype = request.getAllHeaders().get('content-type')
        if ctype == CT_BINARY_PLIST:
            prop = request.uri.rsplit("?", 1)[1]
            parsedbody = read_binary_plist(StringIO(request.content.read()))
            value = parsedbody.get("value")
            self.apserver.set_property(prop, value)
        else:
            raise Exception("Unexpected content type for setProperty: %s" % ctype)
        return ""
