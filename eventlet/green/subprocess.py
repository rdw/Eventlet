import errno
import new
import os

import eventlet
from eventlet import greenio
from eventlet import patcher
from eventlet.green import select

subprocess_orig = __import__("subprocess")
# TODO: eventlet.green.os
patcher.inject('subprocess', globals(), ('select', select))

# This is the meat of this module, the green version of Popen.
class Popen(subprocess_orig.Popen):
    """eventlet-friendly version of subprocess.Popen"""
    # We do not believe that Windows pipes support non-blocking I/O. At least,
    # the Python file objects stored on our base-class object have no
    # setblocking() method, and the Python fcntl module doesn't exist on
    # Windows. (see eventlet.greenio.set_nonblocking()) As the sole purpose of
    # this __init__() override is to wrap the pipes for eventlet-friendly
    # non-blocking I/O, don't even bother overriding it on Windows.
    if not subprocess_orig.mswindows:
        def __init__(self, *args, **kwds):
            # Forward the call to base-class constructor
            subprocess_orig.Popen.__init__(self, *args, **kwds)
            # Now wrap the pipes, if any. This logic is loosely borrowed from 
            # eventlet.processes.Process.run() method.
            for attr in "stdin", "stdout", "stderr":
                pipe = getattr(self, attr)
                if pipe is not None:
                    greenio.set_nonblocking(pipe)
                    wrapped_pipe = greenio.GreenPipe(pipe)
                    # The default 'newlines' attribute is '\r\n', which aren't
                    # sent over pipes.
                    wrapped_pipe.newlines = '\n'
                    setattr(self, attr, wrapped_pipe)
        __init__.__doc__ = subprocess_orig.Popen.__init__.__doc__

    def wait(self, check_interval=0.01):
        # Instead of a blocking OS call, this version of wait() uses logic
        # borrowed from the eventlet 0.2 processes.Process.wait() method.
        try:
            while True:
                status = self.poll()
                if status is not None:
                    return status
                eventlet.sleep(check_interval)
        except OSError, e:
            if e.errno == errno.ECHILD:
                # no child process, this happens if the child process
                # already died and has been cleaned up, or if you just
                # called with a random pid value
                return -1
            else:
                raise
    wait.__doc__ = subprocess_orig.Popen.wait.__doc__

    if not subprocess_orig.mswindows:
        # We don't want to copy/paste all the logic of the original
        # _communicate() method, we just want a version that uses
        # eventlet.green.select.select() instead of select.select().
        _communicate = new.function(subprocess_orig.Popen._communicate.im_func.func_code,
                                    globals())

# Borrow subprocess.call() and check_call(), but patch them so they reference
# OUR Popen class rather than subprocess.Popen.
call       = new.function(subprocess_orig.call.func_code,       globals())
check_call = new.function(subprocess_orig.check_call.func_code, globals())
