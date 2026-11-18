"""Opt-in timing for Tk command families; no widget contents are recorded."""
import time


class TkTiming:
    def __init__(self, interpreter):
        self.interpreter = interpreter
        self.timings = {}

    def __getattr__(self, name):
        return getattr(self.interpreter, name)

    def call(self, *args):
        words = args[0] if args and isinstance(args[0], tuple) else args
        command = str(words[0]) if words else 'empty'
        if command.startswith('.'):
            command = 'widget '+str(words[1] if len(words) > 1 else '')
        elif command in ('wm', 'winfo', 'font', 'image', 'ttk::style') and len(words) > 1:
            command += ' '+str(words[1])
        started = time.perf_counter()
        try:
            return self.interpreter.call(*args)
        finally:
            elapsed = (time.perf_counter()-started)*1000
            timing = self.timings.setdefault(command, dict(count=0, total_ms=0, maximum_ms=0))
            timing['count'] += 1
            timing['total_ms'] += elapsed
            timing['maximum_ms'] = max(timing['maximum_ms'], elapsed)
