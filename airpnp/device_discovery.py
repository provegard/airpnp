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

from upnp import UpnpBase, MSearchRequest, SoapError, SSDPServer
from cStringIO import StringIO
from httplib import HTTPMessage
from twisted.internet import reactor, defer
from twisted.application.service import Service, MultiService
from twisted.application.internet import TimerService
from twisted.python import log
from twisted.web import error
from util import *
from device_builder import DeviceRejectedError, DeviceBuilder


# Seconds between m-search discoveries
DISCOVERY_INTERVAL = 300


class DeviceDiscoveryService(MultiService):

    """Service that discovers and tracks UPnP devices.

    Once started, this service will monitor the network for UPnP devices of a
    specific type. If a device is found, the on_device_found(device) method is
    called. When a device disappears, the on_device_removed(device) method is
    called. A client should subclass this class and implement those methods.

    """

    def __init__(self, ip_addr, sn_types=[], device_types=[], required_services=[]): # pylint: disable-msg=W0102
        """Initialize the service.

        Arguments:
        ip_addr           -- IP address for listening services.
        sn_types          -- list of device and/or service types to look for in
                             UPnP notifications and responses; other types will
                             be ignored. "upnp:rootdevice" is automatically
                             tracked, and should not be in this list.
        device_types      -- list of interesting device types, used to filter
                             out devices based on their "deviceType" attribute.
                             An empty list means that all types are interesting.
        required_services -- if non-empty, list of services that the device
                             must have for it to be considered

        """
        MultiService.__init__(self)
        self._builders = {}
        self._devices = {}
        self._ignored = []
        self._sn_types = ['upnp:rootdevice'] + sn_types
        self._dev_types = device_types
        self._req_services = required_services
        self._ip_addr = ip_addr

        # create the UPnP listener service
        UpnpService(self._datagram_handler, ip_addr).setServiceParent(self)
        
        # create the periodic M-SEARCH request service
        msearch = MSearchRequest(self._datagram_handler)
        TimerService(DISCOVERY_INTERVAL, self._msearch_discover,
                     msearch).setServiceParent(self)

    def _is_device_interesting(self, device):
        # the device must have an approved device type
        if len(self._dev_types) > 0 and not device.deviceType in self._dev_types:
            reason = "device type %s is not recognized" % (device.deviceType, )
            return False, reason

        # the device must contain all required services
        req_services = set(self._req_services)
        act_services = set([s.serviceId for s in device])
        if not req_services.issubset(act_services):
            missing = req_services.difference(act_services)
            reason = "services %s are missing" % (list(missing), )
            return False, reason

        # passed all tests, device is interesting
        return True, None

    def on_device_found(self, device):
        """Called when a device has been found."""
        pass

    def on_device_removed(self, device):
        """Called when a device has disappeared."""
        pass

    def _datagram_handler(self, datagram, address):
        """Process incoming datagram, either response or notification."""
        umessage = UpnpMessage(datagram)
        if umessage.is_notification():
            self._handle_notify(umessage)
        else:
            self._handle_response(umessage)

    def _handle_notify(self, umessage):
        """Handle a notification message from a device."""
        udn = umessage.get_udn()
        if not udn in self._ignored:
            nts = umessage.get_notification_sub_type()
            if nts == 'ssdp:alive':
                self._handle_response(umessage)
            elif nts == 'ssdp:byebye':
                self._device_expired(umessage.get_udn())

    def _device_expired(self, udn):
        """Handle a bye-bye message from a device, or lack of renewal."""
        if udn in self._devices:
            builder = self._builders.pop(udn, None)
            if builder:
                builder.cancel()
            mgr = self._devices.pop(udn)
            log.msg('Device %s expired or said goodbye' % (mgr.device, ), ll=2)
            mgr.stop()
            self.on_device_removed(mgr.device)

    def _handle_response(self, umessage):
        """Handle response to M-SEARCH message."""
        udn = umessage.get_udn()
        if udn and not udn in self._ignored:
            mgr = self._devices.get(udn)
            if mgr:
                mgr.touch(umessage)
            elif not udn in self._builders:
                self._build_device(umessage)

    def _build_device(self, umessage):
        """Start building a device if it seems to be a proper one."""
        if umessage.get_type() in self._sn_types:
            udn = umessage.get_udn()
            builder = DeviceBuilder(self._send_soap_message,
                                    self._is_device_interesting)
            d = builder.build(umessage.get_location())
            
            d.addCallback(self._device_finished, umessage)
            d.addErrback(self._device_error, udn)

            log.msg("Starting build of device with UDN = %s" % (udn, ), ll=3)
            self._builders[udn] = d

    def _send_soap_message(self, device, url, msg, async=False, deferred=None):
        """Send a SOAP message and do error handling."""
        def log_answer(response):
            if isinstance(response, SoapError):
                log.msg('Error response for %s command from %s: %s/%s' %
                        (msg.get_name(), device.friendlyName, response.code, response.desc))
            else:
                log.msg('Got SOAP response from %s: %s' %
                        (device.friendlyName, format_soap_message(response)), ll=3)
            return response
        try:
            log.msg('Sending SOAP message to %s: %s' %
                    (device.friendlyName, format_soap_message(msg)), ll=3)
            if async:
                answer = send_soap_message_deferred(url, msg, deferred=deferred)
                answer.addCallback(log_answer)
            else:
                answer = send_soap_message(url, msg)
                log_answer(answer)
            return answer
        except:
            log.err(None, 'Failed to send command "%s" to device %s' %
                    (msg.get_name(), device))

            raise

    def _device_error(self, fail, udn):
        """Handle error that occurred when building a device."""
        if not fail.check(defer.CancelledError):
            del self._builders[udn]
            if fail.check(DeviceRejectedError):
                device = fail.value.device
                log.msg('Adding device %s to ignore list, because %s' %
                        (device, fail.getErrorMessage()), ll=2)
                self._ignored.append(udn)
            elif fail.check(error.Error):
                if hasattr(fail, 'url'):
                    msg = "%s when fetching %s" % (str(fail.value), fail.url)
                else:
                    msg = str(fail.value)
                log.msg('Adding UDN %s to ignore list, because %s' % (udn, msg), ll=2)
                self._ignored.append(udn)
            else:
                log.err(fail, "Failed to build Device with UDN %s" % (udn, ))

    def _device_finished(self, device, umessage):
        """Handle completion of device building."""
        mgr = DeviceManager(device, self._device_expired)
        self._devices[device.UDN] = mgr

        # Start the device container timer
        mgr.touch(umessage)

        # Publish the device
        self.on_device_found(device)

    def _msearch_discover(self, msearch):
        """Send M-SEARCH device discovery requests."""
        log.msg('Sending out M-SEARCH discovery requests', ll=3)
        ifs = [self._ip_addr]
        # send two requests to counter UDP unreliability
        reactor.callLater(0, msearch.send, reactor, 'ssdp:all', 5,
                          interfaces=ifs)
        reactor.callLater(1, msearch.send, reactor, 'ssdp:all', 5,
                          interfaces=ifs)


class UpnpService(Service):

    def __init__(self, handler, ip_addr):
        self.handler = handler
        self.ip_addr = ip_addr

    def datagramReceived(self, datagram, address, outip):
        self.handler(datagram, address)

    def startService(self):
        Service.startService(self)

        # start ssdp server
        # Binding to an interface binds to an IP address which won't work
        # in the multicast case. SO_BINDTODEVICE solves the problem but
        # it requires root permission.
        self.ssdp = reactor.listenMulticast(UpnpBase.SSDP_PORT,
                                            SSDPServer(self),
                                            listenMultiple=True)
        self.ssdp.setLoopbackMode(1)
        self.ssdp.joinGroup(UpnpBase.SSDP_ADDR, interface=self.ip_addr)

    def stopService(self):
        # stop ssdp server
        self.ssdp.leaveGroup(UpnpBase.SSDP_ADDR, interface=self.ip_addr)
        self.ssdp.stopListening()

        Service.stopService(self)


class DeviceManager(object):

    def __init__(self, device, expire_func):
        self.device = device
        self._expire_timer = None
        self._device_expired = expire_func

    def touch(self, umessage):
        """Start or reset the device timer based on UPnP HTTP headers.

        If the expire timer hasn't been started before, it will be when this
        method is called. Otherwise, the timer will be reset. The timer time
        is taken from the "max-age" directive of the "CACHE-CONTROL" header.

        Arguments:
        headers -- dictionary of UPnP HTTP headers

        """
        seconds = get_max_age(umessage.headers) # TODO
        if seconds:
            udn = umessage.get_udn()
            timer = self._expire_timer
            if timer and timer.active():
                timer.reset(seconds)
            else:
                newtimer = reactor.callLater(seconds, self._device_expired,
                                             udn)
                self._expire_timer = newtimer

    def stop(self):
        """Stop the device timer if it is running."""
        if self._expire_timer and self._expire_timer.active():
            self._expire_timer.cancel()


class UpnpMessage(object):

    def __init__(self, data):
        req_line, headers = data.split('\r\n', 1)

        # HTTPMessage has no proper __repr__, so let's use the dictionary
        dict = HTTPMessage(StringIO(headers)).dict.copy()

        # all header names in the UPnP specs are uppercase
        self.headers = {k.upper(): v for k, v in dict.items()}

        method = req_line.split(' ')[0]

        self._notify = method == 'NOTIFY'

        # Unique Service Name => Unique Device Name + Type
        usn = self.headers.get('USN')
        self._udn, self._type = split_usn(usn) if usn else (None, None)

    def get_udn(self):
        return self._udn

    def get_type(self):
        return self._type

    def is_notification(self):
        return self._notify

    def get_notification_sub_type(self):
        return self.headers['NTS']

    def get_location(self):
        return self.headers['LOCATION']

