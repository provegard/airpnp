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

import new
from upnp import SoapMessage, SoapError, ns
from urlparse import urljoin

__all__ = [
    'Device',
    'Service',
]

# Mandatory XML attributes for a device
DEVICE_ATTRS = ['deviceType', 'friendlyName', 'manufacturer',
                'modelName', 'modelNumber', 'UDN']
#TODO, optional: manufacturerURL, modelDescription, modelNumber, modelURL

# Mandatory XML attributes for a service
SERVICE_ATTRS = ['serviceType', 'serviceId', 'SCPDURL',
                 'controlURL', 'eventSubURL']


def find_elements(element, namespace, path):
    """Find elements based on path relative to an element.

    Arguments:
    element   -- the element the path is relative to
    namespace -- the namespace of all elements in the path
    path      -- the relative path

    Return an iterator with the elements found.

    """
    parts = ['{%s}%s' % (namespace, part) for part in path.split('/')]
    newpath = '/'.join(parts)
    return element.findall(newpath)


def add_xml_attrs(obj, element, namespace, attrs):
    """Add attributes to an object based on XML elements.

    Given a list of XML element names, adds corresponding object attributes and
    values to an object.

    Arguments:
    obj       -- object to add attributes to
    element   -- the element whose child elements are sought based on the
                 attribute names
    namespace -- XML namespace of elements
    attrs     -- list of attribute names, each of which is expected to match
                 the tag name of a child element of the given element

    """
    for attr in attrs:
        val = element.findtext('{%s}%s' % (namespace, attr))
        if val is None:
            raise ValueError('Missing attribute: %s' % (attr, ))
        else:
            val = val.strip()
            setattr(obj, attr, val)


class CommandError(Exception):

    def __init__(self, reason, soap_error):
        Exception.__init__(self, reason)
        self._err = soap_error

    def get_soap_error(self):
        return self._err


class Device(object):

    """Class that represents a UPnP device."""

    def __init__(self, element, base_url):
        """Initialize this Device object.

        When a Device object has been created, its Service objects are not
        fully initialized. The reason for this is that the Device object should
        be possible to inspect for relevance before services are initialized.

        Mandatory child elements of the <device> tag in the device
        configuration are added as object attributes to the newly created
        object.

        Arguments:
        element  -- element that contains device configuration
        base_url  -- the URL where the device configuration resides; used to
                    resolve relative URLs in the configuration

        """
        self._base_url = base_url
        self._services = {}
        for deviceElement in find_elements(element, ns.device, 'device'):
            add_xml_attrs(self, deviceElement, ns.device, DEVICE_ATTRS)
            self._read_services(deviceElement)

    def _read_services(self, element):
        for service in find_elements(element, ns.device,
                                     'serviceList/service'):
            self._add_service(Service(self, service, self._base_url))

    def _add_service(self, service):
        self._services[service.serviceId] = service

    def get_services(self):
        """Return an immutable list of services for this device."""
        return self._services.viewvalues()

    def get_service_ids(self):
        """Return an immutable list of IDs of services for this device."""
        return self._services.viewkeys()

    def get_service_by_id(self, sid):
        """Return a service based on its ID."""
        return self._services[sid]

    def get_base_url(self):
        """Return the base URL of the device configuration."""
        return self._base_url

    def __str__(self):
        return '%s [UDN=%s]' % (self.friendlyName, self.UDN)


class Service(object):

    """Class that represents a UPnP service.

    Once initialized, service actions can be invoked as regular methods,
    although input arguments must be given as a keyword dictionary. Output
    arguments are likewise returned as a dictionary.

    """

    def __init__(self, device, element, base_url):
        """Initialize this Service object partly.

        Initialization of a Service object is done in two steps. Creating
        an object only ensures that mandatory child elements of the <service>
        tag in the device configuration are added as object attributes to the
        newly created object. The initialize method must be called to also
        add service actions as object methods.

        Arguments:
        device   -- the Device object that owns this service
        element  -- element within the device configuration that contains
                    basic service configuration
        base_url -- URL of the device configuration; used to resolve relative
                    URLs found in the service configuration

        """
        add_xml_attrs(self, element, ns.device, SERVICE_ATTRS)
        self._base_url = base_url
        self._resolve_urls([attr for attr in SERVICE_ATTRS if
                            attr.endswith('URL')], base_url)
        self._device = device

    def initialize(self, scpd_element, soap_sender):
        """Initialize this service object with service actions.

        Each service action is added as a method on this object.

        Arguments:
        scpd_element -- service configuration retrieved from the SCPD URL
        soap_sender  -- callable used to send SOAP messages, receives the
                        device, the control URL and the SoapMessage object

        """
        #TODO: better name
        self._add_actions(scpd_element, soap_sender)

    def _add_actions(self, element, soap_sender):
        for action in find_elements(element, ns.service, 'actionList/action'):
            act = Action(self._device, action, soap_sender)
            method = new.instancemethod(act, self, self.__class__)
            setattr(self, act.name, method)

    def _resolve_urls(self, attrs, base_url):
        for attr in attrs:
            val = getattr(self, attr)
            newval = urljoin(base_url, val)
            setattr(self, attr, newval)


class Action(object):

    def __init__(self, device, element, soap_sender):
        add_xml_attrs(self, element, ns.service, ['name'])
        self._arguments = []
        self._add_arguments(element)
        self._soap_sender = soap_sender
        self._device = device

    def _add_arguments(self, element):
        for argument in find_elements(element, ns.service,
                                      'argumentList/argument'):
            self._arguments.append(Argument(argument))

    def __call__(self, service, **kwargs):
        msg = SoapMessage(service.serviceType, self.name)

        # arrange the arguments by direction
        inargs = [arg for arg in self._arguments if arg.direction == 'in']
        outargs = [arg for arg in self._arguments if arg.direction == 'out']

        # update the message with input argument values
        for arg in inargs:
            val = kwargs.get(arg.name)
            if val is None:
                raise KeyError('Missing IN argument: %s' % (arg.name, ))
            msg.set_arg(arg.name, val)

        # send the message
        response = self._soap_sender(self._device, service.controlURL, msg)
        if isinstance(response, SoapError):
            raise CommandError('Command error: %s/%s' % (response.code,
                                                         response.desc),
                               response)
        # populate the output dictionary
        ret = {}
        for arg in outargs:
            ret[arg.name] = response.get_arg(arg.name)
        return ret


class Argument(object):

    def __init__(self, element):
        add_xml_attrs(self, element, ns.service, ['name', 'direction',
                                                  'relatedStateVariable'])
