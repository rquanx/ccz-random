"""Window-owned asynchronous tasks, cancellation and main-thread delivery."""
from concurrent.futures import ThreadPoolExecutor, Future
import threading
import queue
from time import perf_counter
from tkinter import TclError
from ccz_randomizer.ui.window_events import bind_window_event


class WindowTasks:
    def __init__(self, window, *, serial=True, on_close=None):
        self.on_close = on_close
        self.window = window
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="window-task") if serial else None
        self.results = queue.SimpleQueue()
        self.pending = {}
        self.durable = set()
        self.cancel_events = {}
        self.callbacks = {}
        self.generations = {}
        self.closed = False
        self.timer = None
        self._unbind = bind_window_event(window, "<Destroy>", self._destroyed)

    def invalidate(self, key):
        self.generations[key] = self.generations.get(key, 0) + 1
        future = self.pending.pop(key, None)
        self.callbacks.pop(key, None)
        cancel = self.cancel_events.pop(key, None)
        if cancel is not None and key not in self.durable:
            cancel.set()
        if future is not None and key not in self.durable:
            future.cancel()
        self.durable.discard(key)
        if not self.callbacks and self.timer is not None:
            self.window.after_cancel(self.timer)
            self.timer = None

    def _ensure_poll(self):
        if not self.closed and self.callbacks and self.timer is None:
            self.timer = self.window.after(20, self._poll)

    def request(self, key, action, done, failed, *, durable=False, cancel_event=None):
        if self.closed:
            return
        self.invalidate(key)
        if durable:
            self.durable.add(key)
        if cancel_event is not None:
            self.cancel_events[key] = cancel_event
        generation = self.generations[key]
        self.callbacks[key] = (done, failed)
        results = self.results

        def read():
            try:
                result = (True, action())
            except Exception as error:
                result = (False, error)
            # No Tk widgets or UI callbacks may be retained by this thread.
            results.put((key, generation, result))

        if self.executor is not None:
            self.pending[key] = self.executor.submit(read)
        else:
            future = Future()
            self.pending[key] = future
            def run():
                if future.set_running_or_notify_cancel():
                    read()
                    future.set_result(None)
            threading.Thread(target=run, daemon=True, name="window-task").start()
        self._ensure_poll()

    def channel(self, key, callback):
        """Return a worker-safe writer. Only the UI thread invokes callback."""
        self.invalidate(key)
        generation = self.generations[key]
        self.callbacks[key] = (callback, callback)
        self._ensure_poll()
        results = self.results
        return lambda value: results.put((key, generation, (None, value)))

    def _poll(self):
        self.timer = None
        if self.closed:
            return
        started = perf_counter()
        try:
            for _ in range(64):
                if perf_counter() - started >= .008:
                    break
                key, generation, (success, value) = self.results.get_nowait()
                if self.generations.get(key) == generation:
                    if success is None:
                        self.callbacks[key][0](value)
                        if self.closed:
                            return
                        continue
                    self.pending.pop(key, None)
                    self.durable.discard(key)
                    self.cancel_events.pop(key, None)
                    done, failed = self.callbacks.pop(key)
                    (done if success else failed)(value)
                if self.closed:
                    return
        except queue.Empty:
            pass
        finally:
            self._ensure_poll()

    def _destroyed(self, event):
        if event.widget is self.window:
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        self._unbind()
        if self.timer is not None:
            try:
                self.window.after_cancel(self.timer)
            except TclError:
                pass
            self.timer = None
        if self.on_close:
            self.on_close()
        for key, future in self.pending.items():
            if key not in self.durable:
                cancel = self.cancel_events.get(key)
                if cancel is not None:
                    cancel.set()
                future.cancel()
        self.pending.clear()
        self.durable.clear()
        self.cancel_events.clear()
        self.callbacks.clear()
        if self.executor is not None:
            self.executor.shutdown(wait=False, cancel_futures=False)

