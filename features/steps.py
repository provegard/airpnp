from lettuce import *
from base import *

@step("an empty configuration")
def empty_configuration(step):
    world.airpnp_config = {}

@step("I start Airpnp")
def start_airpnp(step):
    world.start_airpnp()

@step('I see the log message "(.*)"')
def see_log_message(step, message):
    found, lines = world.airpnp.read_log_until(".*%s.*" % message)
    assert found == True, "Got log lines: %r" % lines

