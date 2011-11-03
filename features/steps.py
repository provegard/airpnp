from lettuce import *
from base import *
import re

@step("an empty configuration")
def empty_configuration(step):
    world.airpnp_config = {}

@step("I start Airpnp")
def start_airpnp(step):
    world.start_airpnp()

@step('I should see the log message "(.*)"')
def see_log_message(step, message):
    found, lines = world.airpnp.read_lines(".*%s.*" % message)
    assert found == True, "Got log lines: %r" % lines

@step('I will see the following discovery message:')
def see_discovery_message(step):
    found, lines = world.receiver.read_lines("^---done", 5000)
    expected = [str(line) for line in re.split("\r?\n", step.multiline)]
    actual = [line.strip() for line in lines[:-1] if line.strip() != ""]
    assert actual == expected, "Got %r, expected %r" % (actual, expected)

@step('I listen for discovery messages')
def listen_for_discovery_messages(step):
    world.receiver = world.start_process("python ssdp_udp_receiver.py", ".")
