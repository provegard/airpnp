from lettuce import *
from base import *

@world.absorb
def start_airpnp():
    assert not hasattr(world, 'airpnp'), 'Found lingering Airpnp process'
    world.airpnp = AirpnpProcess(world.airpnp_config)
    world.airpnp.start()

@after.each_scenario
def stop_airpnp(scenario):
    if hasattr(world, 'airpnp'):
        world.airpnp.stop()
        world.spew('airpnp') #TODO: or del??

