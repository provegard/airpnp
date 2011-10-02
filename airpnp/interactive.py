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

from twisted.web import server, resource
from twisted.application.internet import TCPServer


class InteractiveWeb(TCPServer):

    def __init__(self, port):
        self.root = self.create_site()
        self.port = port

        TCPServer.__init__(self, port, server.Site(self.root), 100)

    def add_device(self, device):
        devroot = self.create_device_site(device)
        self.root.putChild(str(device), devroot)

    def remove_device(self, device):
        self.root.delEntity(str(device))

    def create_site(self):
        root = resource.Resource()
        main = ListChildrenResource("Devices", root)
        root.putChild("", main)
        return root

    def create_device_site(self, device):
        root = ListChildrenResource("Services")
        for service in device:
            oplist = ListChildrenResource("Operations")
            root.putChild(service.serviceId, oplist)
            for op in service.actions:
                action = getattr(service, op)
                show = ShowOperationResource(device, service, action)
                oplist.putChild(op, show)
                show.putChild("execute", ExecuteOperationResource(action))
        return root


class ExecuteOperationResource(resource.Resource):

    def __init__(self, action):
        resource.Resource.__init__(self)
        self._action = action

    def render_POST(self, request):
        from cgi import escape
        kwargs = {}
        for arg in request.args.keys():
            kwargs[arg] = request.args[arg][0]
        body = ""
        try:
            ret = self._action(**kwargs)
            if len(ret):
                body += '<table border="1"><tr><th>Argument</th><th>Value</th></tr>\n'
                for outarg in ret.keys():
                    value = escape(str(ret[outarg]))
                    body += "<tr><td>%s</td><td><tt>%s</tt></td></tr>\n" % \
                            (outarg, value)
                body += "</table>\n"
            else:
                body += "<p>No output arguments</p>\n"
        except BaseException, e:
            body += "<p>ERROR: %s</p>\n" % (e, )

        body += '<form enctype="application/x-www-form-urlencoded" ' \
                'method="post" action="execute">\n'
        for arg in kwargs:
            body += '<input type="hidden" name="%s" value="%s" />\n' % \
                    (arg, kwargs[arg])
        body += '<input type="submit" name="submit" value="Refresh" />\n'
        body += "</form>"

        return create_html(request, "%s Response" % (self._action.name, ), body)


class ShowOperationResource(resource.Resource):

    def __init__(self, device, service, action):
        resource.Resource.__init__(self)
        self.service = service
        self.device = device
        self.action = action

    def render_GET(self, request):
        body = "<h1>%s::%s</h1>" % (self.service.serviceId, self.action.name)
        body += '<form enctype="application/x-www-form-urlencoded" ' \
                'method="post" action="%s">\n' % (request.childLink("execute"), )
        body += '<table border="0">\n'
        args = self.action.arguments
        inargs = [arg for arg in args if arg.direction == 'in']
        for arg in inargs:
            body += '<tr><td><label for="%s">%s</label></td><td>' \
                    '<input type="text" name="%s" /></td></tr>\n' \
                    % (arg.name, arg.name, arg.name)
        body += '</table>\n'
        body += '<input type="submit" name="submit" value="Execute" />\n'
        body += "</form>"
        title = "%s::%s @ %s" % (self.service.serviceId, self.action.name,
                                 self.device.friendlyName)
        return create_html(request, title, body)


class ListChildrenResource(resource.Resource):

    def __init__(self, title, parent=None):
        resource.Resource.__init__(self)
        self._parent = parent if parent is not None else self
        self._title = title

    def render_GET(self, request):
        body = "<h1>%s</h1>\n" % (self._title, )
        for name in self._parent.children.keys():
            if name:
                link = request.childLink(name)
                body += '<p><a href="./%s">%s</a></p>\n' % (link, name)
        return create_html(request, "Listing of " + self._title, body)


def create_html(request, title, body):
    navbar = ""
    base = "/"
    prepath = list(request.prepath)
    if len(prepath) == 0 or not prepath[0] == "":
        prepath.insert(0, "")
    for part in prepath[:-1]:
        path = base + part
        if part != "":
            base += part + "/"
        title = part if part != "" else "root"
        navbar += '<a href="%s">%s</a> &gt; ' % (path, title)
    html = """<html>
<head>
    <title>%s</title>
</head>
<body>
%s
<hr />
%s
</body>
</html>""" % (title, body, navbar)
    return html
