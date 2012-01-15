import sys
import re
from subprocess import PIPE, Popen, STDOUT
from threading  import Thread
import os
import os.path
import tempfile
import shlex

from Queue import Queue, Empty

ON_POSIX = 'posix' in sys.builtin_module_names

__all__ = [
    "Process",
    "AirpnpProcess",
]

def enqueue_output(out, queue):
    for line in iter(out.readline, ''):
        queue.put(line)
    out.close()

def millis():
    import time as time_ #make sure we don't override time
    return int(round(time_.time() * 1000))


class Process(object):

    def __init__(self, command_line, cwd='.'):
        self.command_line = command_line
        self.cwd = os.path.join(os.path.dirname(__file__), cwd)

    def start(self):
        args = shlex.split(self.command_line)
        self.proc = Popen(args, stdout=PIPE, stderr=STDOUT, cwd=self.cwd, close_fds=ON_POSIX, bufsize=1)
        self.q = Queue()
        t = Thread(target=enqueue_output, args=(self.proc.stdout, self.q))
        t.daemon = True
        t.start()
        return self

    def stop(self):
        self.proc.kill()

    def read_lines(self, line_pattern=None, timeout=1000):
        if not hasattr(self, 'lines'):
            self.lines = []
        if line_pattern is None:
            pat = None
        else:
            pat = re.compile(line_pattern)
        found = False
        start = millis()
        block = False
        get_timeout = None
        while True:
            try:
                line = self.q.get(block, timeout=get_timeout)
                self.lines.append(line)
                if pat and pat.match(line):
                    found = True
                    break
            except Empty:
                if line_pattern and millis() < start + timeout:
                    block = True
                    get_timeout = 0.1
                else:
                    break
        return found, self.lines

class AirpnpProcess(Process):

    def __init__(self, config=None):
        configfn = self.create_config(config)
        pidfile = self.create_pidfile()
        self.todelete = [configfn, pidfile]
        self.stopped = False
        command_line = "twistd --pidfile=%s -n airpnp -c %s" % (pidfile, configfn)
        Process.__init__(self, command_line, cwd="..")

    def create_pidfile(self):
        f = tempfile.NamedTemporaryFile()
        f.close()
        return f.name

    def create_config(self, config):
        if config is None:
            config = {}
        else:
            config = config.copy()
        #TODO: externally configured interface!!
        #config['interface'] = '127.0.0.1'
        config['loglevel'] = '4'
        f = tempfile.NamedTemporaryFile(delete=False)
        f.write("[airpnp]\n")
        for k, v in config.items():
            f.write("%s=%s\n" % (k, v))
        f.close()
        return f.name

    def stop(self):
        Process.stop(self)
        self.delfiles()
        self.stopped = True

    def delfiles(self):
        for f in [ff for ff in self.todelete if os.path.exists(ff)]:
            os.unlink(f)

    def __del__(self):
        if not self.stopped:
            self.delfiles()

