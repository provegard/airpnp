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

from xml.etree import ElementTree as ET
from device import Device
from twisted.internet import defer
from twisted.web import client


__all__ = [
    'DeviceRejectedError',
    'DeviceBuilder',
]


class DeviceRejectedError(Exception):
    """Raised by a DeviceBuilder if a device is rejected by a filter."""

    def __init__(self, device, *args):
        self.device = device
        Exception.__init__(self, *args)


class DeviceBuilder(object):
    """Device builder that builds a Device object from a remote location.

    The device builder downloads the XML definition of the root device from the
    given location, and continues to download service information if the device
    passes the initial filter.

    """

    def __init__(self, soap_sender, filter_=None):
        """Initialize a device builder.

        Arguments:
        soap_sender -- passed to the created Device object
        filter_     -- optional callable that receives the created device to
                       determine if the builder should continue with service
                       initialization. Should return a tuple of (bool, string),
                       where the bool is the continue flag, and the string is
                       a reason in case the continue flag is False.

        """
        self._filter = filter_
        self._soap_sender = soap_sender

    def _check_filter(self, device):
        if self._filter:
            accepted, reason = self._filter(device)
            if not accepted:
                raise DeviceRejectedError(device, reason)
        return device

    def _init_service(self, element, service):
        service.initialize(element, self._soap_sender)
        return service

    def _get_device(self, result):
        """Get the device from a list of tuples of (success, result), where the
        result is a Service object.
        """
        return result[0][1].device

    def _init_services(self, device):
        def start_init_service(service):
            d = client.getPage(service.SCPDURL, timeout=5)
            d.addCallback(ET.fromstring)
            d.addCallback(self._init_service, service)
            return d
        dl = [start_init_service(s) for s in device]
        return defer.DeferredList(dl)

    def build(self, location):
        """Build a Device object from a remote location.

        Arguments:
        location -- the HTTP URL where the root device XML can be found

        Return a Deferred which will callback when the Device object is ready.
        The caller must add an errback to handle errors raised during the build
        process.

        """
        d = defer.succeed(location)

        # get the device XML
        d.addCallback(client.getPage, timeout=5)

        # parse it to an element
        d.addCallback(ET.fromstring)

        # create a new Device object
        d.addCallback(Device, location)

        # check if the device passes the filter
        d.addCallback(self._check_filter)

        # initialize services
        d.addCallback(self._init_services)

        # make sure the Device object is returned
        d.addCallback(self._get_device)

        return d
