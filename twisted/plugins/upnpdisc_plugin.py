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

import common
from zope.interface import implements
from twisted.application.service import IServiceMaker, MultiService
from twisted.plugin import IPlugin
from twisted.python import log

from airpnp.config import config
from airpnp.device_discovery import DeviceDiscoveryService


class MainService(DeviceDiscoveryService):

    def __init__(self, ip):
        DeviceDiscoveryService.__init__(self, ip)

    def on_device_found(self, device):
        log.msg("Found device %s @ %s" % (device, device.get_base_url()))
        for service in device:
            log.msg(" -- service %s of type %s" % (service.serviceId, service.serviceType)) 

    def on_device_removed(self, device):
        log.msg("Lost device %s" % (device, ))


class MyServiceMaker(object):
    implements(IServiceMaker, IPlugin)
    tapname = "upnpdisc"
    description = "UPnP Device Disocvery."
    options = common.Options

    def makeService(self, options):
        common.loadconfig(options)
        common.tweak_twisted()
        return MainService(config.interface_ip())


serviceMaker = MyServiceMaker()
