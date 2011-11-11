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

import re
import inspect
from zope.interface import implements
from twisted.internet import protocol
from twisted.python import log
from twisted.plugin import IPlugin

from airpnp.config import config

# Log level if not specified
DEFAULT_LOG_LEVEL = 1

# Log level for Twisted's log messages
TWISTED_LOG_LEVEL = 4

def get_calling_module():
    frm = inspect.stack()[2][0]
    try:
        return inspect.getmodule(frm)
    finally:
        # http://docs.python.org/library/inspect.html#the-interpreter-stack
        del frm


def patch_log(oldf):
    def mylog(*message, **kw):
        # Get the log level, if any
        ll = kw.has_key('ll') and kw['ll'] or DEFAULT_LOG_LEVEL

        # Adjust log level for Twisted's messages
        module = get_calling_module().__name__
        if module.startswith('twisted.') and not re.match("twisted\.plugins\..*_plugin", module):  
            ll = TWISTED_LOG_LEVEL

        # Log if level is on or below the configured limit
        if ll <= config.loglevel():
            nkw = kw.copy()
            nkw['system'] = "%s/%d" % (module, ll)
            oldf(*message, **nkw)
    return mylog


def tweak_twisted():
    # Turn off noisiness on some of Twisted's classes
    protocol.AbstractDatagramProtocol.noisy = False
    protocol.Factory.noisy = False

    # Patch logging to introduce log level support
    log.msg = patch_log(log.msg)

