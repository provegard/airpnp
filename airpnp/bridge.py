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

import aplog as log
from device_discovery import DeviceDiscoveryService
from AirPlayService import AirPlayService, AirPlayOperations
from util import hms_to_sec, sec_to_hms
from config import config


MEDIA_RENDERER_DEVICE_TYPE = 'urn:schemas-upnp-org:device:MediaRenderer:1'
MEDIA_RENDERER_TYPES = [MEDIA_RENDERER_DEVICE_TYPE,
                        'urn:schemas-upnp-org:service:AVTransport:1',
                        'urn:schemas-upnp-org:service:ConnectionManager:1',
                        'urn:schemas-upnp-org:service:RenderingControl:1']

CN_MGR_SERVICE = 'urn:upnp-org:serviceId:ConnectionManager'
AVT_SERVICE = 'urn:upnp-org:serviceId:AVTransport'


class BridgeServer(DeviceDiscoveryService):

    _ports = []

    def __init__(self):
        DeviceDiscoveryService.__init__(self, MEDIA_RENDERER_TYPES,
                                        [MEDIA_RENDERER_DEVICE_TYPE])

    def on_device_found(self, device):
        log.msg(1, 'Found device %s with base URL %s' % (device,
                                                         device.get_base_url()))
        cpoint = AVControlPoint(device)
        avc = AirPlayService(cpoint, device.friendlyName, port=self._find_port())
        avc.setName(device.UDN)
        avc.setServiceParent(self)

    def on_device_removed(self, device):
        log.msg(1, 'Lost device %s' % (device, ))
        avc = self.getServiceNamed(device.UDN)
        avc.disownServiceParent()
        self._ports.remove(avc.port)

    def _find_port(self):
        port = 22555
        while port in self._ports:
            port += 1
        self._ports.append(port)
        return port


class AVControlPoint(AirPlayOperations):

    _uri = None
    _pre_scrub = None
    _position_pct = None
    _client = None
    _instance_id = None

    def __init__(self, device):
        self._connmgr = device.get_service_by_id(CN_MGR_SERVICE)
        self._avtransport = device.get_service_by_id(AVT_SERVICE)
        self.msg = lambda ll, msg: log.msg(ll, '(-> %s) %s' % (device, msg))

    @property
    def client(self):
        return self._client

    @client.setter
    def client(self, value):
        if not value is None and not self._client is None:
            log.msg(1, "Rejecting client %r since device is busy (current "
                    "client = %r)" % (value, self._client))
            raise ValueError("Device is busy")
        self._client = value
        if value is None:
            self._release_instance_id(self._instance_id)
        else:
            self._instance_id = self._allocate_instance_id()

    def get_scrub(self):
        posinfo = self._avtransport.GetPositionInfo(
            InstanceID=self._instance_id)
        if not self._uri is None:
            duration = hms_to_sec(posinfo['TrackDuration'])
            position = hms_to_sec(posinfo['RelTime'])
            self.msg(2, 'Scrub requested, returning duration %f, position %f' %
                     (duration, position))

            if not self._position_pct is None:
                self._try_seek_pct(duration, position)

            return duration, position
        else:
            return 0.0, 0.0

    def is_playing(self):
        if self._uri is not None:
            state = self._get_current_transport_state()
            playing = state == 'PLAYING'
            self.msg(2, 'Play status requested, returning %s' % (playing, ))
            return playing
        else:
            return False

    def _get_current_transport_state(self):
        stateinfo = self._avtransport.GetTransportInfo(
            InstanceID=self._instance_id)
        return stateinfo['CurrentTransportState']

    def set_scrub(self, position):
        if self._uri is not None:
            hms = sec_to_hms(position)
            self.msg(2, 'Scrubbing/seeking to position %f' % (position, ))
            self._avtransport.Seek(InstanceID=self._instance_id,
                                   Unit='REL_TIME', Target=hms)
        else:
            self.msg(2, 'Saving scrub position %f for later' % (position, ))

            # save the position so that we can user it later to seek
            self._pre_scrub = position

    def play(self, location, position):
        if config.loglevel() >= 2:
            self.msg(2, 'Starting playback of %s at position %f' %
                     (location, position))
        else:
            self.msg(1, 'Starting playback of %s' % (location, ))


        # start loading of media, also set the URI to indicate that
        # we're playing
        self._avtransport.SetAVTransportURI(InstanceID=self._instance_id,
                                            CurrentURI=location,
                                            CurrentURIMetaData='')
        self._uri = location

        # start playing also
        self._avtransport.Play(InstanceID=self._instance_id, Speed='1')

        # if we have a saved scrub position, seek now
        if not self._pre_scrub is None:
            self.msg(2, 'Seeking based on saved scrub position')
            self.set_scrub(self._pre_scrub)

            # clear it because we have used it
            self._pre_scrub = None
        else:
            # no saved scrub position, so save the percentage position,
            # which we can use to seek once we have a duration
            self._position_pct = float(position)

    def stop(self, info):
        if self._uri is not None:
            self.msg(1, 'Stopping playback')
            self._avtransport.Stop(InstanceID=self._instance_id)

            # clear the URI to indicate that we don't play anymore
            self._uri = None

            # clear the client, so that we can accept another
            self.client = None

    def reverse(self, info):
        pass

    def rate(self, speed):
        if self._uri is not None:
            if (int(float(speed)) >= 1):
                state = self._get_current_transport_state()
                if not state == 'PLAYING' and not state == 'TRANSITIONING':
                    self.msg(1, 'Resuming playback')
                    self._avtransport.Play(InstanceID=self._instance_id,
                                           Speed='1')
                else:
                    self.msg(2, 'Rate ignored since device state is %s' %
                             (state, ))

                if not self._position_pct is None:
                    duration, pos = self.get_scrub()
                    self._try_seek_pct(duration, pos)
            else:
                self.msg(1, 'Pausing playback')
                self._avtransport.Pause(InstanceID=self._instance_id)

    def _try_seek_pct(self, duration, position):
        if duration > 0:
            self.msg(2, ('Has duration %f, can calculate position from ' +
                         'percentage %f') % (duration, self._position_pct))
            targetoffset = duration * self._position_pct

            # clear the position percentage now that we've used it
            self._position_pct = None

            # do the actual seeking
            if targetoffset > position:  # TODO: necessary?
                self.set_scrub(targetoffset)

    def _allocate_instance_id(self):
        iid = '0'
        if hasattr(self._connmgr, 'PrepareForConnection'):
            self.msg(2, 'ConnectionManager::PrepareForConnection not implemented!')
        return iid

    def _release_instance_id(self, instance_id):
        if hasattr(self._connmgr, 'ConnectionComplete'):
            self.msg(2, 'ConnectionManager::ConnectionComplete not implemented!')
