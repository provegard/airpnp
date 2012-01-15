from lettuce import *
from base import *

@world.absorb
def start_airpnp():
    assert not hasattr(world, 'airpnp'), 'Found lingering Airpnp process'
    if hasattr(world, 'airpnp_config'):
        config = world.airpnp_config
    else:
        config = {}
    world.airpnp = AirpnpProcess(config).start()

@world.absorb
def start_process(cmd_line, cwd="."):
    if not hasattr(world, 'processes'):
        world.processes = []
    proc = Process(cmd_line, cwd=cwd).start()
    world.processes.append(proc)
    return proc

@after.each_scenario
def clear_airpnp_config(scenario):
    world.spew('airpnp_config')

@after.each_scenario
def stop_airpnp(scenario):
    if hasattr(world, 'airpnp'):
        world.airpnp.stop()
        world.spew('airpnp') #TODO: or del??

@after.each_scenario
def stop_processes(scenario):
    if hasattr(world, 'processes'):
        while len(world.processes) > 0:
            proc = world.processes.pop()
            proc.stop()

