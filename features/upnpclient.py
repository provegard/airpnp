#!/usr/bin/python

import re
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from airpnp.upnp import *
from uuid import uuid1
from twisted.internet import reactor


class Client(object):

    def __init__(self, basedir, udn, name):
        self.basedir = basedir
        self.udn = udn
        self.name = name
        self.root = self.create_temp_root()
        self.prepare()

    def prepare(self):
        dd = os.path.join(self.basedir, self.root)
        device = UpnpDevice(self.udn, dd, self.soap_app)
        self.base = UpnpBase()
        self.base.append_device([device])

    def create_temp_root(self):
        fd, path = tempfile.mkstemp(suffix=".xml", dir=self.basedir, text=True)
        dst = os.fdopen(fd, "w")
        with open(os.path.join(self.basedir, "root.xml")) as src:
            while 1:
                buf = src.read(8192)
                buf = re.sub("<friendlyName\\s*/>",
                             "<friendlyName>%s</friendlyName>" % self.name, buf)
                if buf:
                    dst.write(buf)
                else:
                    break
        dst.close()
        return path

    def soap_app(self, environ, start_response):
        sid = environ['wsgiorg.routing_args'][1]['sid']
        serviceType = environ['upnp.soap.serviceType']
        action = environ['upnp.soap.action']
        req = SoapMessage.parse(StringIO(environ['upnp.body']), serviceType, action)

        return not_found(environ, start_response)

    def start(self, reactor):
        self.base.start(reactor)

    def stop(self):
        self.base.remove_device(self.udn)
        self.base.stop()
        os.unlink(self.root)


def main(reactor):
    basedir, udn, name = sys.argv[1:4]

    print "Base directory = %s" % basedir
    print "UDN = %s" % udn
    print "Friendly name = %s" % name

    #uuid:Samsung-Printer-1_0-LASER

    client = Client(basedir, udn, name)
    reactor.addSystemEventTrigger("before", "shutdown", client.stop)
    client.start(reactor)

if __name__ == '__main__':
    reactor.callWhenRunning(main, reactor)
    reactor.run()

