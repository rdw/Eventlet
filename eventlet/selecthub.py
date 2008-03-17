"""\
@file selecthub.py
@author Bob Ippolito

Copyright (c) 2005-2006, Bob Ippolito
Copyright (c) 2007, Linden Research, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import sys
import select
import errno
import traceback
import time
from bisect import insort, bisect_left

from eventlet import greenlib
from eventlet import hub

import greenlet

class Hub(hub.Hub):
    def add_descriptor(self, fileno, read=None, write=None, exc=None):
        self.readers[fileno] = read
        self.writers[fileno] = write
        self.excs[fileno] = exc
        
    def remove_descriptor(self, fileno):
        self.readers[fileno] = None
        self.writers[fileno] = None
        self.excs[fileno] = None

    def exc_descriptor(self, fileno):
        # We must handle two cases here, the descriptor
        # may be changing or removing its exc handler
        # in the queue, or it may be waiting on the queue.
        exc = self.excs.get(fileno)
        if exc is not None:
            try:
                exc(fileno)
            except self.SYSTEM_EXCEPTIONS:
                self.squelch_exception(fileno, sys.exc_info())
    
    def wait(self, seconds=None):
        self.process_queue()
        readers = self.readers
        writers = self.writers
        excs = self.excs
        if not readers and not writers and not excs:
            if seconds:
                time.sleep(seconds)
            return
        try:
            r, w, ig = select.select(readers.keys(), writers.keys(), [], seconds)
        except select.error, e:
            if e.args[0] == errno.EINTR:
                return
            raise
        SYSTEM_EXCEPTIONS = self.SYSTEM_EXCEPTIONS
        for observed, events in ((readers, r), (writers, w)):
            for fileno in events:
                try:
                    observed[fileno](fileno)
                except SYSTEM_EXCEPTIONS:
                    raise
                except:
                    self.squelch_exception(fileno, sys.exc_info())
