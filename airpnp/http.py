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

from config import config
from twisted.web import server, resource, static
from twisted.application.internet import TCPServer


__all__ = [
    'HTTPServer',
    'DynamicResourceServer',
]


class HTTPSite(server.Site):
    """A Site subclass that sets the noisiness of the created channels based on
    the current log level."""

    def buildProtocol(self, addr):
        channel = server.Site.buildProtocol(self, addr)
        channel.noisy = config.loglevel() >= 3
        return channel


class HTTPServer(TCPServer):
    """A TCP server that uses a HTTPSite instance as protocol factory.

    Resources are added after initialization using the add_resources method.
    Exposes the actual port as a data attribute named 'port'. This is useful if
    port 0 was specified for the server. Note that the port number won't be
    available until the server has been started.

    """

    def __init__(self, port, backlog):
        self.root = resource.Resource()
        site = HTTPSite(self.root)
        TCPServer.__init__(self, port, site, backlog)

    def add_resources(self, resource_dict):
        """Add one or more named resources to the root resource.

        Arguments:
        resource_dict -- dictionary of resources to add

        """
        for name in resource_dict:
            self.root.putChild(name, resource_dict[name])

    def startService(self):
        TCPServer.startService(self)
        self.port = self._port.getHost().port


class DynamicResourceServer(HTTPServer):
    """A HTTPServer sub class that allows content to be published dynamically at
    the root level, and later on unpublished.

    """

    def publish(self, name, content_type, data):
        """Publish data of a given content type under the given name.

        Arguments:
        name         -- the name/path of the resource to add
        content_type -- the content type of the data
        data         -- the data that will be returned for the resource

        """
        res = static.Data(data, content_type)
        self.add_resources({name: res})

    def unpublish(self, name):
        """Unpublishes named data previously published using the 'publish'
        method.
        
        Arguments:
        name -- the name of the published resource
        
        """
        self.root.delEntity(name)
