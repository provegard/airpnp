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

import logging
from device_discovery import DeviceDiscoveryService
from AirPlayService import AirPlayService
from util import hms_to_sec, sec_to_hms


MEDIA_RENDERER_DEVICE_TYPE = 'urn:schemas-upnp-org:device:MediaRenderer:1'
MEDIA_RENDERER_TYPES = [MEDIA_RENDERER_DEVICE_TYPE,
                        'urn:schemas-upnp-org:service:AVTransport:1',
                        'urn:schemas-upnp-org:service:ConnectionManager:1',
                        'urn:schemas-upnp-org:service:RenderingControl:1']

CN_MGR_SERVICE = 'urn:upnp-org:serviceId:ConnectionManager'
AVT_SERVICE = 'urn:upnp-org:serviceId:AVTransport'

log = logging.getLogger("airpnp.bridge-server")


class BridgeServer(DeviceDiscoveryService):

    _ports = []

    def __init__(self):
        DeviceDiscoveryService.__init__(self, MEDIA_RENDERER_TYPES,
                                        [MEDIA_RENDERER_DEVICE_TYPE])

    def on_device_found(self, device):
        log.info('Found device %s with base URL %s' % (device,
                                                       device.get_base_url()))
        avc = AVControlPoint(device, port=self._find_port())
        avc.setName(device.UDN)
        avc.setServiceParent(self)

    def on_device_removed(self, device):
        log.info('Lost device %s' % (device, ))
        avc = self.getServiceNamed(device.UDN)
        avc.disownServiceParent()

    def _find_port(self):
        port = 22555
        while port in self._ports:
            port += 1
        self._ports.append(port)
        return port


class AVControlPoint(AirPlayService):

    _uri = None
    _pre_scrub = None
    _position_pct = None

    def __init__(self, device, host="0.0.0.0", port=22555):
        AirPlayService.__init__(self, device.friendlyName, host, port)
        self._connmgr = device.get_service_by_id(CN_MGR_SERVICE)
        self._avtransport = device.get_service_by_id(AVT_SERVICE)
        self._instance_id = self._allocate_instance_id()
        self.port = port

    def stopService(self):
        self._release_instance_id(self._instance_id)
        return AirPlayService.stopService(self)

    def get_scrub(self):
        posinfo = self._avtransport.GetPositionInfo(
            InstanceID=self._instance_id)
        if not self._uri is None:
            duration = hms_to_sec(posinfo['TrackDuration'])
            position = hms_to_sec(posinfo['RelTime'])
            log.debug(('get_scrub -> GetPositionInfo -> %s, %s -> ' +
                      'returning %f, %f') % (posinfo['TrackDuration'],
                                             posinfo['RelTime'], duration,
                                             position))

            if not self._position_pct is None:
                self._try_seek_pct(duration, position)

            return duration, position
        else:
            log.debug('get_scrub -> (no URI) -> returning 0.0, 0.0')
            return 0.0, 0.0

    def is_playing(self):
        if self._uri is not None:
            state = self._get_current_transport_state()
            playing = state == 'PLAYING'
            log.debug('is_playing -> GetTransportInfo -> %s -> returning %r' %
                      (state, playing))
            return playing
        else:
            log.debug('is_playing -> (no URI) -> returning False')
            return False

    def _get_current_transport_state(self):
        stateinfo = self._avtransport.GetTransportInfo(
            InstanceID=self._instance_id)
        return stateinfo['CurrentTransportState']

    def set_scrub(self, position):
        if self._uri is not None:
            hms = sec_to_hms(position)
            log.debug('set_scrub (%f) -> Seek (%s)' % (position, hms))
            self._avtransport.Seek(InstanceID=self._instance_id,
                                   Unit='REL_TIME', Target=hms)
        else:
            log.debug('set_scrub (%f) -> (no URI) -> saved for later' %
                      (position, ))

            # save the position so that we can user it later to seek
            self._pre_scrub = position

    def play(self, location, position):
        log.debug('play (%s, %f) -> SetAVTransportURI + Play' % (location,
                                                                 position))

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
            log.debug('Seeking based on saved scrub position')
            self.set_scrub(self._pre_scrub)

            # clear it because we have used it
            self._pre_scrub = None
        else:
            # no saved scrub position, so save the percentage position,
            # which we can use to seek once we have a duration
            self._position_pct = float(position)

    def stop(self, info):
        if self._uri is not None:
            log.debug('stop -> Stop')
            self._avtransport.Stop(InstanceID=self._instance_id)

            # clear the URI to indicate that we don't play anymore
            self._uri = None
        else:
            log.debug('stop -> (no URI) -> ignored')

    def reverse(self, info):
        pass

    def rate(self, speed):
        if self._uri is not None:
            if (int(float(speed)) >= 1):
                state = self._get_current_transport_state()
                if not state == 'PLAYING' and not state == 'TRANSITIONING':
                    log.debug('rate(%r) -> Play' % (speed, ))
                    self._avtransport.Play(InstanceID=self._instance_id,
                                           Speed='1')
                else:
                    log.debug('rate(%r) -> ignored due to state %s' % (speed,
                                                                       state))

                if not self._position_pct is None:
                    duration, pos = self.get_scrub()
                    self._try_seek_pct(duration, pos)
            else:
                log.debug('rate(%r) -> Pause' % (speed, ))
                self._avtransport.Pause(InstanceID=self._instance_id)

    def _try_seek_pct(self, duration, position):
        if duration > 0:
            log.debug(('Has duration %f, can calculate position from ' +
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
            log.warn('ConnectionManager::PrepareForConnection not implemented')
        return iid

    def _release_instance_id(self, instance_id):
        if hasattr(self._connmgr, 'ConnectionComplete'):
            log.warn('ConnectionManager::ConnectionComplete not implemented')
