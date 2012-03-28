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

import uuid
from device import CommandError
from device_discovery import DeviceDiscoveryService
from airplayserver import IAirPlayServer
from AirPlayService import AirPlayService
from upnp import parse_duration, to_duration
from config import config
from util import get_image_type, create_device_id
from interactive import InteractiveWeb
from zope.interface import implements
from twisted.internet import defer
from twisted.application.internet import TCPServer
from twisted.web import server, resource, static
from twisted.python import log

MEDIA_RENDERER_DEVICE_TYPE = 'urn:schemas-upnp-org:device:MediaRenderer:1'
AVTRANSPORT_SERVICE_TYPE = 'urn:schemas-upnp-org:service:AVTransport:1'
CONNMANAGER_SERVICE_TYPE = 'urn:schemas-upnp-org:service:ConnectionManager:1'
RENDERINGCTRL_SERVICE_TYPE = 'urn:schemas-upnp-org:service:RenderingControl:1'

# List of types that trigger the build of a device
MEDIA_RENDERER_TYPES = [MEDIA_RENDERER_DEVICE_TYPE, AVTRANSPORT_SERVICE_TYPE,
                        CONNMANAGER_SERVICE_TYPE, RENDERINGCTRL_SERVICE_TYPE]

# List of service types that a device must have
REQ_SERVICE_TYPES = [AVTRANSPORT_SERVICE_TYPE, CONNMANAGER_SERVICE_TYPE]


class BridgeServer(DeviceDiscoveryService):

    def __init__(self, interface):
        DeviceDiscoveryService.__init__(self, interface[0], MEDIA_RENDERER_TYPES,
                                        [MEDIA_RENDERER_DEVICE_TYPE],
                                        REQ_SERVICE_TYPES)

        self._ports = []
        
        # optionally add a server for the Interactive Web
        if config.interactive_web_enabled():
            iwebport = config.interactive_web_port()
            self.iweb = InteractiveWeb(iwebport, interface[0])
            self.iweb.setServiceParent(self)
        else:
            self.iweb = None

        # add a server for serving photos to UPnP devices
        self.photoweb = PhotoWeb(0, 5, interface[0])
        self.photoweb.setServiceParent(self)

        self.interface = interface

    def startService(self):
        log.msg("Airpnp started. Will now search for UPnP devices!")

        if self.iweb:
            # apparently, logging in __init__ is too early
            iwebport = self.iweb.port
            log.msg("Starting interactive web at port %d" % (iwebport, ))
        DeviceDiscoveryService.startService(self)

    def on_device_found(self, device):
        log.msg('Found device %s with base URL %s' % (device,
                                                      device.get_base_url()))
        cpoint = AVControlPoint(device, self.photoweb, self.interface[0])
        devid = create_device_id(device.UDN)
        avc = AirPlayService(cpoint, device.friendlyName, host=self.interface[0], port=self._find_port(), index=self.interface[1], device_id=devid)
        avc.setName(device.UDN)
        avc.setServiceParent(self)
        
        if self.iweb:
            self.iweb.add_device(device) 

    def on_device_removed(self, device):
        log.msg('Lost device %s' % (device, ))
        avc = self.getServiceNamed(device.UDN)
        avc.disownServiceParent()
        self._ports.remove(avc.port)
        del avc

        if self.iweb:
            self.iweb.remove_device(device)

    def _find_port(self):
        port = 22555
        while port in self._ports:
            port += 1
        self._ports.append(port)
        return port


class AVControlPoint(object):

    implements(IAirPlayServer)

    _uri = None
    _client = None
    _instance_id = None
    _photo = None
    _play_pos = None

    def __init__(self, device, photoweb, ip_addr):
        self._connmgr = [s for s in device if s.serviceType ==
                         CONNMANAGER_SERVICE_TYPE][0]
        self._avtransport = [s for s in device if s.serviceType ==
                             AVTRANSPORT_SERVICE_TYPE][0]
        self.msg = lambda ll, msg: log.msg('(-> %s) %s' % (device.friendlyName, msg), ll=ll)
        self._photoweb = photoweb
        self._instance_id = self.allocate_instance_id()
        self._ip_addr = ip_addr
    
    def __del__(self):
        self.release_instance_id(self._instance_id)

    def _log_async(self, value, log_level, msg):
        self.msg(log_level, msg % (value, ))
        return value

    def set_session_id(self, sid):
        pass

    def get_scrub(self):
        def parse_posinfo(posinfo):
            duration = parse_duration(posinfo['TrackDuration'])
            position = parse_duration(posinfo['RelTime'])
            return duration, position
        
        def maybe_seek(dp):
            duration, position = dp
            if duration > 0 and not self._play_pos is None:
                seek_pos = duration * self._play_pos
                self._play_pos = None
                self.msg(2, 'Consumed cached play position')
                # if the device has played past the seek position, don't
                # do anything because that would be annoying!
                if seek_pos > position:
                    self.set_scrub(seek_pos)
            return dp

        if self._uri:
            # async call, returns a Deferred
            d = self._avtransport.GetPositionInfo(InstanceID=self._instance_id, async=True)
            d.addCallback(parse_posinfo)
            d.addCallback(maybe_seek) # 
            d.addCallback(self._log_async, 2, 'Scrub requested, returning duration, position: %r')
            return d
        else:
            return defer.succeed((0.0, 0.0))

    def is_playing(self):
        if self._uri:
            # async call, returns a Deferred
            d = self._avtransport.GetTransportInfo(InstanceID=self._instance_id, async=True)
            d.addCallback(lambda stateinfo: stateinfo['CurrentTransportState'] == 'PLAYING')
            d.addCallback(self._log_async, 2, 'Play status requested, returning %r')
            return d
        else:
            return defer.succeed(False)

    def _get_current_transport_state(self):
        stateinfo = self._avtransport.GetTransportInfo(InstanceID=self._instance_id)
        return stateinfo['CurrentTransportState']

    def set_scrub(self, position):
        if self._uri:
            hms = to_duration(position)
            self.msg(2, 'Scrubbing/seeking to position %f' % (position, ))
            self._avtransport.Seek(InstanceID=self._instance_id, Unit='REL_TIME', Target=hms)

    def play(self, location, position):
        if config.loglevel() >= 2:
            self.msg(2, 'Starting playback of %s (requested position is %f)' %
                     (location, position))
        else:
            self.msg(1, 'Starting playback of %s' % (location, ))

        # start loading of media, state should still be STOPPED
        self._avtransport.SetAVTransportURI(InstanceID=self._instance_id, CurrentURI=location, CurrentURIMetaData='')

        # indicate that we're playing, and save the requested position
        # to be consumed later when the device knows the duration!
        self._uri = location        
        self._play_pos = position

    def stop(self):
        if self._uri:
            self.msg(1, 'Stopping playback')
            if not self.stop_ignoring_718():
                self.msg(1, "Failed to stop playback, device may still be in a playing state")

            # clear the URI to indicate that we don't play anymore
            self._uri = None            
            self._play_pos = None

            # unpublish any published photo
            if not self._photo is None:
                self._photoweb.unpublish(self._photo)
                self._photo = None
                
    def stop_ignoring_718(self):
        try:
            self._avtransport.Stop(InstanceID=self._instance_id)
            return True
        except CommandError, e:
            soap_err = e.get_soap_error()
            if soap_err.code != '718':
                raise
            return False

    def reverse(self, proxy):
        pass

    def rate(self, speed):
        if self._uri:
            if int(float(speed)) >= 1:
                self.msg(1, 'Starting/resuming playback')
                self._avtransport.Play(InstanceID=self._instance_id, Speed='1')
            else:
                self.msg(1, 'Pausing playback')
                self._avtransport.Pause(InstanceID=self._instance_id)

    def photo(self, data, transition):
        ctype, ext = get_image_type(data)

        # create a random name for the photo
        name = str(uuid.uuid4()) + ext

        # remove any previous photo
        if self._photo:
            self._photoweb.unpublish(self._photo)

        # publish the new photo
        self._photoweb.publish(name, ctype, data)
        self._photo = name

        # create the URI
        hostname = self._ip_addr
        uri = "http://%s:%d/%s" % (hostname, self._photoweb.port, name)

        self.msg(1, "Showing photo, published at %s" % (uri, ))

        # start loading of media, also set the URI to indicate that
        # we're playing
        # Note: if we already have a photo, this would be a good time to call
        # SetNextAVTransportURI, but I have no media renderer that supports it.
        self._avtransport.SetAVTransportURI(InstanceID=self._instance_id,
                                            CurrentURI=uri,
                                            CurrentURIMetaData='')
        self._uri = uri

        # show the photo (no-op if we're already playing)
        self._avtransport.Play(InstanceID=self._instance_id, Speed='1')

    def set_property(self, name, value):
        pass

    def allocate_instance_id(self):
        iid = '0'
        if hasattr(self._connmgr, 'PrepareForConnection'):
            self.msg(2, 'ConnectionManager::PrepareForConnection not implemented!')
        return iid

    def release_instance_id(self, instance_id):
        if hasattr(self._connmgr, 'ConnectionComplete'):
            self.msg(2, 'ConnectionManager::ConnectionComplete not implemented!')


class PhotoWeb(TCPServer):

    def __init__(self, port, backlog, ip_addr):
        self.root = resource.Resource()
        TCPServer.__init__(self, port, server.Site(self.root), backlog, interface=ip_addr)

    def publish(self, name, content_type, data):
        self.root.putChild(name, static.Data(data, content_type))

    def unpublish(self, name):
        self.root.delEntity(name)
        
    @property
    def port(self):
        return self._port.getHost().port

