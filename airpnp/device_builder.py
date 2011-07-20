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

from util import split_usn, fetch_url
from xml.etree import ElementTree
from device import Device
from twisted.python import log

__all__ = [
    'AsyncDeviceBuilder',
    'DeviceEvent',
    'DeviceContainer',
]


class DeviceContainer(object):

    """Container for a Device object.
    
    An instance is initialized from a dictionary of HTTP headers, from which
    the USN is extracted and split into UDN and service/device type. A Device
    object can be attached using the set_device(device) method.

    """

    # Attribute for the attached Device object.
    _device = None

    def __init__(self, headers):
        """Initialize this object from a dictionary of HTTP headers.
        
        The "USN" header must be present in the dictionary, or a KeyError will
        be raised. The headers are stored for later retrieval.

        """
        usn = headers['USN']
        self._udn, self._type = split_usn(usn)
        self._headers = headers

    def get_udn(self):
        """Return the UDN extracted during object initialization.
        
        The UDN is extracted from the USN header.

        """
        return self._udn

    def get_type(self):
        """Return the device/service type extracted during initialization.
        
        The typs is extracted from the USN header. If the USN header does not
        contain a type, the return string is the empty string.

        """
        return self._type

    def get_headers(self):
        """Return the dictionary of HTTP headers passed to the constructor."""
        return self._headers

    def set_device(self, device):
        """Attach a Device object to this container."""
        self._device = device

    def get_device(self):
        """Return the Device object from this container.
        
        If no Device object has been attached, return None.

        """
        return self._device

    def has_device(self):
        """Determine if this container has an attached Device object."""
        return not self._device is None


class DeviceEvent(object):

    """Event class for events fired from an AsyncDeviceBuilder."""

    def __init__(self, source, device_container, error=None):
        """Initialize a new event object.

        Arguments:
        source           -- the originator of the event (typically the builder)
        device_container -- the DeviceContainer instance passed to the builder
        error            -- an error object if an error was raised

        """
        self._source = source
        self._device_container = device_container
        self._error = error

    def get_udn(self):
        """Return the UDN of the Device associated with this event."""
        return self._device_container.get_udn()

    def get_device(self):
        """Return the Device object associated with this event."""
        return self._device_container.get_device()

    def get_source(self):
        """Return the originator of this event."""
        return self._source

    def get_error(self):
        """Return the error, if any, associated with this event.
        
        If no error occurred during Device building, return None.

        """
        return self._error


class AsyncDeviceBuilder(object):

    """Device builder that builds a Device object from UPnP HTTP headers.

    The device builder extracts the location of the root device from the
    "LOCATION" header, and downloads device information from there. If the
    device type passes a predefined filter, the builder continues to download
    and initialize device services.

    The device building is asynchronous, and executes in a separate thread.

    Upon completion, filter rejection or error, an event is fired to registered
    listeners (each of which must be a callable). The listener received a
    single DeviceEvent object.

    """

    # List of listeners for 'finished' events.
    _finished_listeners = []

    # List of listeners for 'rejected' events.
    _rejected_listeners = []

    # List of listeners for 'error' events.
    _error_listeners = []

    def __init__(self, reactor, soap_sender, filter_=None):
        """Initialize a device builder.

        Arguments:
        reactor     -- Twisted reactor used for asynchronous operation.
        soap_sender -- passed to the created Device object
        filter_     -- optional callable that receives the created device to
                       determine if the builder should continue with service
                       initialization

        If the filter returns False for a device, a 'rejected' event will be
        fired to registered listeners.

        """
        self.reactor = reactor
        self._filter = filter_
        self._soap_sender = soap_sender

    def add_finished_listener(self, listener):
        """Add a listener for 'finished' events.
        
        A 'finished' event is fired when a device has been built and its
        services have been initialized. The listener must be a callable, and
        will receive a DeviceEvent object.
        
        """
        self._finished_listeners.append(listener)

    def add_rejected_listener(self, listener):
        """Add a listener for 'rejected' events.
        
        A 'rejected' event is fired when a device has been built, but the
        filter passed to the constructor has rejected the device by returning
        False. The services of the Device object are not initialized. The
        listener must be a callable, and will receive a DeviceEvent object.
        
        """
        self._rejected_listeners.append(listener)

    def add_error_listener(self, listener):
        """Add a listener for 'error' events.
        
        An 'error' event is fired if an error is raised during device building.
        The listener must be a callable, and will receive a DeviceEvent object.
        
        """
        self._error_listeners.append(listener)

    def build(self, container):
        """Build a Device object asynchronously.

        Arguments:
        container -- DeviceContainer instance that contains UPnP HTTP headers
                     that point to required device resources

        """
        self.reactor.callInThread(self._create_device, container)

    def _create_device(self, container):
        try:
            # create a new Device and attach it to the container
            device = self._new_device(container)
            container.set_device(device)

            # determine if the device is accepted
            accepted = self._filter is None or self._filter(device)

            # if so, continue with services, otherwise we're done
            if accepted:
                # init each service
                for service in device.get_services():
                    self._init_service(service)

                # finished, back to main thread
                self.reactor.callFromThread(self._device_finished, container)
            else:
                # rejected device, back to main thread
                self.reactor.callFromThread(self._device_rejected, container)
        except BaseException, err:
            log.err(err, 'Failed to create Device object')
            # error, back to main thread
            self.reactor.callFromThread(self._device_error, err, container)

    def _init_service(self, service):
        scpd_handle = fetch_url(service.SCPDURL)
        scpd_element = ElementTree.parse(scpd_handle)
        service.initialize(scpd_element, self._soap_sender)

    def _new_device(self, container):
        location = self._get_location(container)
        handle = fetch_url(location)
        element = ElementTree.parse(handle)
        return Device(element, location)

    def _get_location(self, container):
        headers = container.get_headers()
        return headers['LOCATION']

    def _device_finished(self, container):
        event = DeviceEvent(self, container)
        fire_event(event, self._finished_listeners)

    def _device_rejected(self, container):
        event = DeviceEvent(self, container)
        fire_event(event, self._rejected_listeners)

    def _device_error(self, error, container):
        event = DeviceEvent(self, container, error)
        fire_event(event, self._error_listeners)


def fire_event(event, listener_list):
    for listener in listener_list:
        listener(event)
