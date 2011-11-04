import sys
from subprocess import PIPE, Popen, STDOUT
from threading  import Thread
import os.path
import tempfile

from Queue import Queue, Empty

ON_POSIX = 'posix' in sys.builtin_module_names

__all__ = [
    "read_until",
    "AirpnpProcess",
]

def enqueue_output(out, queue):
    for line in iter(out.readline, ''):
        queue.put(line)
    out.close()

def millis():
    import time as time_ #make sure we don't override time
    return int(round(time_.time() * 1000))

def read_until(q, pattern, timeout=1000):
    import re
    start = millis()
    lines = []
    pat = re.compile(pattern)
    found = False
    while millis() - start < timeout:
        try:
            line = q.get(timeout=.2)
            lines.append(line)
            if pat.match(line):
                found = True
                break
        except Empty:
            pass
    return (found, lines)

class AirpnpProcess(object):

    def __init__(self, config={}):
        self.config = config

    def create_config(self, config):
        f = tempfile.NamedTemporaryFile(delete=True)
        f.write("[airpnp]\n")
        for k, v in config.items():
            f.write("%s=%s\n" % (k, v))
        f.flush()
        return f.name

    def __enter__(self):
        configfn = self.create_config(self.config)
        args = ["twistd", "-n", "airpnp", "-c", configfn]
        cwd = os.path.join(os.path.dirname(__file__), "..")
        self.proc = Popen(args, stdout=PIPE, stderr=STDOUT, cwd=cwd, close_fds=ON_POSIX, bufsize=1)
        q = Queue()
        t = Thread(target=enqueue_output, args=(self.proc.stdout, q))
        t.daemon = True
        t.start()
        return q

    def __exit__(self, type, value, tb):
        self.proc.kill()


