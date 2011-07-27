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

import sys
import aplog as log
from upnp import UpnpBase, MSearchRequest, SoapError
from cStringIO import StringIO
from httplib import HTTPMessage
from twisted.internet import reactor
from twisted.application.service import Service, MultiService
from twisted.application.internet import TimerService
from util import send_soap_message, split_usn, get_max_age
from device_builder import AsyncDeviceBuilder, DeviceContainer

# Seconds between m-search discoveries
DISCOVERY_INTERVAL = 300


class ActiveDeviceContainer(DeviceContainer):

    """DeviceContainer sub class that adds the notion of an active device.

    The first time a client calls the touch(headers) method, a timer is started
    based on the "max-age" directive in the "CACHE-CONTROL" HTTP header. 
    Subsequent calls to the touch(headers) method renew (reset) the timer. When
    the timer has reached zero, an event is fired to all 'expire' listeners.

    """

    # Expire timer, initially not created
    _expire_timer = None

    # List of 'expire' listeners
    _expire_listeners = []

    def add_expire_listener(self, listener):
        """Add an 'expire' listener.
        
        The listener must be a callable and will receive the UDN of the device
        whose timer has expired.

        """
        self._expire_listeners.append(listener)

    def touch(self, headers):
        """Start or reset the device timer based on UPnP HTTP headers.

        If the expire timer hasn't been started before, it will be when this
        method is called. Otherwise, the timer will be reset. The timer time
        is taken from the "max-age" directive of the "CACHE-CONTROL" header.

        Arguments:
        headers -- dictionary of UPnP HTTP headers

        """
        device = self.get_device()
        seconds = get_max_age(headers)
        if not seconds is None:
            udn = device.UDN
            timer = self._expire_timer
            if timer is None or not timer.active():
                newtimer = reactor.callLater(seconds, self._device_expired,
                                             udn)
                self._expire_timer = newtimer
            else:
                timer.reset(seconds)

    def stop(self):
        """Stop the device timer if it is running."""
        if not self._expire_timer is None and self._expire_timer.active():
            self._expire_timer.cancel()

    def _device_expired(self, udn):
        """Handle the case when a device hasn't renewed itself."""
        for listener in self._expire_listeners:
            listener(udn)


class DeviceDiscoveryService(MultiService):

    """Service that discovers and tracks UPnP devices.

    Once started, this service will monitor the network for UPnP devices of a
    specific type. If a device is found, the on_device_found(device) method is
    called. When a device disappears, the on_device_removed(device) method is
    called. A client should subclass this class and implement those methods.

    """

    # Dictionary of DeviceContainer objects, keyed by UDN
    _devices = {}

    # List of UDNs of devices that are being ignored
    _ignored = []

    # Device/service types to look for
    _sn_types = ['upnp:rootdevice']

    def __init__(self, sn_types=[], device_types=[]): # pylint: disable-msg=W0102
        """Initialize the service.

        Arguments:
        sn_types     -- list of device and/or service types to look for; other
                        types will be ignored. "upnp:rootdevice" is
                        automatically tracked, and should not be in this list.
        device_types -- list of interesting device types, used to filter out
                        devices based on their "deviceType" attribute

        """
        MultiService.__init__(self)
        self._sn_types.extend(sn_types)
        self._dev_types = device_types
        self._builder = self._create_device_builder()

        # create the UPnP listener service
        UpnpService(self._datagram_handler).setServiceParent(self)
        
        # create the periodic M-SEARCH request service
        msearch = MSearchRequest(self._datagram_handler)
        TimerService(DISCOVERY_INTERVAL, self._msearch_discover,
                     msearch).setServiceParent(self)

    def _create_device_builder(self):
        builder = AsyncDeviceBuilder(reactor, self._send_soap_message,
                                     lambda device: device.deviceType
                                     in self._dev_types)
        builder.add_finished_listener(self._device_finished)
        builder.add_rejected_listener(self._device_rejected)
        builder.add_error_listener(self._device_error)

        return builder

    def on_device_found(self, device):
        """Called when a device has been found."""
        pass

    def on_device_removed(self, device):
        """Called when a device has disappeared."""
        pass

    def _datagram_handler(self, datagram, address):
        """Process incoming datagram, either response or notification."""
        req_line, data = datagram.split('\r\n', 1)
        headers = HTTPMessage(StringIO(data))
        method = req_line.split(' ')[0]
        if method == 'NOTIFY':
            self._handle_notify(headers)
        else:
            self._handle_response(headers)

    def _handle_notify(self, headers):
        """Handle a notification message from a device."""
        nts = headers['NTS']
        udn = split_usn(headers['USN'])[0]
        if not udn in self._ignored:
            if nts == 'ssdp:alive':
                self._handle_response(headers)
            elif nts == 'ssdp:byebye':
                self._device_expired(udn)

    def _device_expired(self, udn):
        """Handle a bye-bye message from a device, or lack of renewal."""
        if udn in self._devices:
            adc = self._devices.pop(udn)
            device = adc.get_device()
            log.msg(2, 'Device %s expired or said goodbye' % (device, ))
            adc.stop()
            self.on_device_removed(device)

    def _handle_response(self, headers):
        """Handle response to M-SEARCH message."""
        usn = headers.get('USN')
        if not usn is None:
            udn = split_usn(usn)[0]
            if not udn in self._ignored:
                adc = self._devices.get(udn)
                if adc is None:
                    self._new_device(headers)
                elif adc.has_device():
                    adc.touch(headers)

    def _new_device(self, headers):
        """Start building a device if it seems to be a proper one."""
        adc = ActiveDeviceContainer(headers)
        if adc.get_type() in self._sn_types:
            # Put the device container in our dictionary before starting the
            # asyncrhonous build, as a guard so that we won't try multiple
            # builds for the same device.
            self._devices[adc.get_udn()] = adc
            self._builder.build(adc)

    def _send_soap_message(self, device, url, msg):
        """Send a SOAP message and do error handling."""
        try:
            log.msg(3, 'Sending SOAP message to device %s:\n%s' %
                    (device, msg.tostring()))
            answer = send_soap_message(url, msg)
            log.msg(3, 'Got response from device %s:\n%s' % (device,
                                                             answer.tostring()))
            if isinstance(answer, SoapError):
                log.msg(1, 'Error response for %s command to device %s: %s/%s' %
                        (msg.get_name(), device, answer.code, answer.desc))

                # hide the device for a short while, hoping that the error is
                # only temporary
                reactor.callLater(0, self._flip, device, reactor)
            return answer
        except:
            error = sys.exc_info()[0]
            log.err(error, 'Failed to send command "%s" to device %s' %
                    (msg.get_name(), device))

            # treat the device as lost
            reactor.callLater(0, self._device_expired, device.UDN)

            raise error

    def _flip(self, device, reactor):
        """Simulate a temporary device removal."""
        self.on_device_removed(device)
        reactor.callLater(1, self.on_device_found, device)

    def _device_error(self, event):
        """Handle error that occurred when building a device."""
        # Remove the device so that we retry it on the next notify
        # or m-search result.
        device = self._devices.pop(event.get_udn())
        device.stop()

    def _device_rejected(self, event):
        """Handle device reject, mismatch against desired device type."""
        udn = event.get_udn()
        adc = self._devices.pop(udn)
        adc.stop()
        log.msg(2, 'Adding device %s to ignore list' % (adc.get_device(), ))
        self._ignored.append(udn)

    def _device_finished(self, event):
        """Handle completion of device building."""
        device = event.get_device()

        # Start the device container timer
        adc = self._devices[event.get_udn()]
        adc.add_expire_listener(self._device_expired)
        adc.touch(adc.get_headers())

        # Publish the device
        self.on_device_found(device)

    def _msearch_discover(self, msearch):
        """Send M-SEARCH device discovery requests."""
        log.msg(3, 'Sending out M-SEARCH discovery requests')
        reactor.callLater(0, msearch.send, reactor, 'ssdp:all', 5)
        reactor.callLater(1, msearch.send, reactor, 'ssdp:all', 5)


class UpnpService(UpnpBase, Service):

    def __init__(self, handler):
        UpnpBase.__init__(self)
        self.handler = handler

    def datagramReceived(self, datagram, address, outip):
        self.handler(datagram, address)

    def startService(self):
        Service.startService(self)
        self.start(reactor)

    def stopService(self):
        self.stop()
        Service.stopService(self)
