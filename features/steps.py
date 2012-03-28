from lettuce import *
from base import *
import re

def find_pattern(pattern, process, timeout):
    found = False
    lines = []
    for l in process.read_lines(timeout):
        lines.append(l)
        if re.search(pattern, l):
            found = True
            break
    return found, lines

@step(u'an empty configuration')
def empty_configuration(step):
    world.airpnp_config = {}

@step(u'Airpnp is started')
def start_airpnp(step):
    world.start_airpnp()

@step('the log should contain the message "(.*)"')
def see_log_message(step, message):
    pattern = ".*%s.*" % re.escape(message)
    found, lines = find_pattern(pattern, world.airpnp, 10000)
    assert found == True, "Got log lines: %r" % lines

@step(u'an? (.*) with UDN (.*) and name (.*) is running')
def media_renderer_is_running(step, device, udn, name):
    # args are unicode, need to convert to str first!
    device = str(device).replace(" ", "")
    cmd = "python upnpclient.py %s %s %s" % (device, str(udn), str(name))
    world.start_process(cmd)

@step(u'Then an AirPlay service is published with the name (.*)')
def airplay_service_published(step, name):
    browser = world.start_process("avahi-browse -prk _airplay._tcp")
    pattern = "^=.*;%s;" % re.escape(name)
    found, lines = find_pattern(pattern, browser, 10000)
    assert found == True, "Got log lines: %r" % lines
    world.airplay_service_lines = [l for l in lines if l.startswith("=")]

@step(u'And the AirPlay service has features set to (.*)')
def and_the_airplay_service_has_features_set_to_0x77(step, features):
    lines = world.airplay_service_lines
    matches = [l for l in lines if l.find("features=" + features) != -1]
    assert len(matches) > 0

@step(u'And the AirPlay service has model set to (.*)')
def and_the_airplay_service_has_model_set_to_appletv2_1(step, model):
    lines = world.airplay_service_lines
    matches = [l for l in lines if l.find("model=" + model) != -1]
    assert len(matches) > 0

@step(u'Then (.*) AirPlay services with name prefix (.*) are published')
def then_2_airplay_services_are_published(step, count, prefix):
    browser = world.start_process("avahi-browse -prk _airplay._tcp")
    services = []
    for l in browser.read_lines(10000):
        parts = l.split(";")
        if parts[0] == "=" and parts[2] == "IPv4" and parts[3].startswith(prefix):
            services.append(l)
    world.airplay_service_lines = services
    assert len(world.airplay_service_lines) == int(count)

@step(u'And the AirPlay services have different device IDs')
def and_the_airplay_services_have_different_device_ids(step):
    devids = [re.search('"deviceid=([:a-zA-Z0-9]+)"', line).group(1) for line in
              world.airplay_service_lines]
    unique = len(set(devids))
    assert unique == len(devids), "Found device IDs: " + str(devids)

