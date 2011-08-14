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

import aplog as log
from twisted.web import resource, server
from twisted.internet import reactor
from http import HTTPSite

__all__ = [
    'BaseResource',
    'AirPlayServer',
    'SessionRejectedError',
    'AirPlayOperationsBase',
]


class SessionRejectedError(Exception):
    pass


class AirPlayOperationsBase(object):

    def set_session_id(self, sid):
        """Set the current session ID.

        Set the current session ID, as repored by the AirPlay client. If another
        session is already ongoing, raise a SessionRejectedError.

        """


class BaseResource(resource.Resource):

    def __init__(self, ops):
        resource.Resource.__init__(self)
        if not isinstance(ops, AirPlayOperationsBase):
            raise ValueError("Operations instance must be of type "
                             "AirPlayOperationsBase.")
        self.ops = ops

    def render(self, request):
        sid = request.getHeader("x-apple-session-id")
        ret = ""
        try:
            self.ops.set_session_id(sid)
            ret = resource.Resource.render(self, request)
        except SessionRejectedError:
            request.setResponseCode(503)
        except:
            log.err(None, "Failed to process AirPlay request")
            request.setResponseCode(501)
        return ret


class AirPlayServer(HTTPSite):
    pass
