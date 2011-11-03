#!/usr/bin/python

from twisted.internet.protocol import DatagramProtocol
from twisted.internet import reactor
import re
import sys

SSDP_HOST = '239.255.255.250'
SSDP_PORT = 1900
BIND_IFACE = '127.0.0.1'

def log(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()

class UPnPReceiver(DatagramProtocol):
    def startProtocol(self):
        self.transport.joinGroup(SSDP_HOST, interface=BIND_IFACE)

    def datagramReceived(self, data, (host, port)):
        if host == BIND_IFACE:
            lines = re.split("\r?\n", data)
            for line in lines:
                log(line.strip())
            log("---done")
            #reactor.stop()

def main():
    multi = reactor.listenMulticast(SSDP_PORT, UPnPReceiver(), listenMultiple=True)

if __name__ == "__main__":
    reactor.callWhenRunning(main)
    reactor.run()
