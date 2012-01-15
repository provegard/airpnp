from lettuce import *
from base import *
import re

@step(u'an empty configuration')
def empty_configuration(step):
    world.airpnp_config = {}

@step(u'Airpnp is started')
def start_airpnp(step):
    world.start_airpnp()

@step('the log should contain the message "(.*)"')
def see_log_message(step, message):
    found, lines = world.airpnp.read_lines(".*%s.*" % re.escape(message), 10000)
    assert found == True, "Got log lines: %r" % lines

@step(u'a (.*) with UDN (.*) and name (.*) is running')
def media_renderer_is_running(step, device, udn, name):
    # args are unicode, need to convert to str first!
    device = str(device).replace(" ", "")
    cmd = "python upnpclient.py %s %s %s" % (device, str(udn), str(name))
    world.start_process(cmd)

@step(u'Then an AirPlay service is published with the name (.*)')
def airplay_service_published(step, name):
    browser = world.start_process("avahi-browse -prk _airplay._tcp")
    found, lines = browser.read_lines("^=.*;%s;" % re.escape(name), 10000)
    assert found == True, "Got log lines: %r" % lines
    world.airplay_service_lines = [l for l in lines if l.startswith("=")]

@step(u'And the AirPlay service has features set to (.*)')
def and_the_airplay_service_has_features_set_to_0x77(step, features):
    matches = [l for l in world.airplay_service_lines
               if l.find("features=" + features) != -1]
    assert len(matches) > 0

@step(u'And the AirPlay service has model set to (.*)')
def and_the_airplay_service_has_model_set_to_appletv2_1(step, model):
    matches = [l for l in world.airplay_service_lines
               if l.find("model=" + model) != -1]
    assert len(matches) > 0

