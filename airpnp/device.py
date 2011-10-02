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

from upnp import SoapMessage, SoapError, ns, toxpath
from urlparse import urljoin

__all__ = [
    'Device',
    'Service',
]

# Mandatory XML attributes for a device
DEVICE_ATTRS = ['deviceType', 'friendlyName', 'manufacturer',
                'modelName', 'UDN']
#TODO, optional: manufacturerURL, modelDescription, modelNumber, modelURL

# Mandatory XML attributes for a service
SERVICE_ATTRS = ['serviceType', 'serviceId', 'SCPDURL',
                 'controlURL', 'eventSubURL']
            
            
class XMLAttributeMixin(object):
    
    def __getattr__(self, name):
        if not name in self.xmlattrs:
            raise NameError(name)
        return self.element.findtext(toxpath(name, self.xmlnamespace)).strip()


class CommandError(Exception):

    def __init__(self, reason, soap_error):
        Exception.__init__(self, reason)
        self._err = soap_error

    def get_soap_error(self):
        return self._err


class Device(XMLAttributeMixin):
    """Class that represents a UPnP device."""
    
    xmlattrs = DEVICE_ATTRS
    xmlnamespace = ns.device

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
        self.element = element.find(toxpath('device', ns.device))
        self._read_services(self.element)

    def _read_services(self, element):
        for service in element.findall(toxpath('serviceList/service', ns.device)):
            s = Service(self, service, self._base_url)
            self._services[s.serviceId] = s

    def __iter__(self):
        for s in self._services:
            yield s

    def __getitem__(self, key):
        """Return a service based on its ID."""
        return self._services[key]

    def get_base_url(self):
        """Return the base URL of the device configuration."""
        return self._base_url

    def __str__(self):
        return '%s [UDN=%s]' % (self.friendlyName, self.UDN)


class Service(XMLAttributeMixin):
    """Class that represents a UPnP service.

    Once initialized, service actions can be invoked as regular methods,
    although input arguments must be given as a keyword dictionary. Output
    arguments are likewise returned as a dictionary.

    """

    xmlattrs = SERVICE_ATTRS
    xmlnamespace = ns.device

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
        self.element = element
        self._base_url = base_url
        self.device = device
        self.actions = {}

    def initialize(self, scpd_element, soap_sender):
        """Initialize this service object with service actions.

        Each service action is added as a method on this object.

        Arguments:
        scpd_element -- service configuration retrieved from the SCPD URL
        soap_sender  -- callable used to send SOAP messages, receives the
                        device, the control URL and the SoapMessage object

        """
        self._add_actions(scpd_element, soap_sender)

    def _add_actions(self, element, soap_sender):
        for action in element.findall(toxpath('actionList/action', ns.service)):
            act = Action(self, action, soap_sender)
            self.actions[act.name] = act
            setattr(self, act.name, act)
            
    def __getattr__(self, name):
        value = super(Service, self).__getattr__(name)
        if name.endswith('URL'):
            value = urljoin(self._base_url, value)
        return value


class Action(XMLAttributeMixin):

    xmlattrs = ['name']
    xmlnamespace = ns.service

    def __init__(self, service, element, soap_sender):
        self.element = element
        self.arguments = []
        self._add_arguments(element)
        self._soap_sender = soap_sender
        self.service = service
        self.inargs = [arg for arg in self.arguments if arg.direction == 'in']
        self.outargs = [arg for arg in self.arguments if arg.direction == 'out']

    def _add_arguments(self, element):
        for argument in element.findall(toxpath('argumentList/argument', ns.service)):
            self.arguments.append(Argument(argument))

    def __call__(self, *args, **kwargs):
        msg = SoapMessage(self.service.serviceType, self.name)

        # see it there is an async flag, defaults to False
        async = bool('async' in kwargs and kwargs.pop('async'))

        # there may be a starting deferred also; only relevant
        # if in async mode
        deferred = 'deferred' in kwargs and kwargs.pop('deferred')

        # update the message with input argument values
        for arg in self.inargs:
            val = kwargs.get(arg.name)
            if val is None:
                raise KeyError('Missing IN argument: %s' % (arg.name, ))
            msg.set_arg(arg.name, val)

        # send the message
        result = self._soap_sender(self.service.device, self.service.controlURL,
                                   msg, async=async, defrerred=deferred)

        if async:
            # assume it's a Deferred
            result.addCallback(decode_soap, self.outargs)
            return result
        else:
            return decode_soap(result, self.outargs)


class Argument(XMLAttributeMixin):
    
    xmlattrs = ['name', 'direction', 'relatedStateVariable']
    xmlnamespace = ns.service

    def __init__(self, element):
        self.element = element


def decode_soap(msg, outargs):
    if isinstance(msg, SoapError):
        raise CommandError('Command error: %s/%s' % (msg.code, msg.desc),
                           msg)

    ret = {}
    for arg in outargs:
        ret[arg.name] = msg.get_arg(arg.name)
    return ret
