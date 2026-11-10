"""Strict unit runner: surface background errors and release Tk objects on the owner thread."""
from __future__ import annotations

import argparse
import gc
import faulthandler
import os
import random
import sys
import threading
import tkinter as tk
import traceback
import unittest
from unittest.mock import patch


class BackgroundErrors:
    def __init__(self):
        self.errors = []

    def capture(self, kind, exception_type, exception, tb):
        self.errors.append(kind + ": " + "".join(traceback.format_exception(exception_type, exception, tb)))

    def thread_error(self, args):
        self.capture("线程异常", args.exc_type, args.exc_value, args.exc_traceback)

    def unraisable_error(self, args):
        self.capture("对象清理异常", args.exc_type, args.exc_value, args.exc_traceback)

    def tk_error(self, _root, exception_type, exception, tb):
        self.capture("Tk 回调异常", exception_type, exception, tb)


class StrictResult(unittest.TextTestResult):
    def startTest(self, test):
        # Cyclic Tk objects must be reclaimed before another test starts a worker.
        gc.collect()
        self.environment = dict(os.environ)
        self.background = BackgroundErrors()
        self.hooks = [patch.object(threading, "excepthook", self.background.thread_error),
                      patch.object(sys, "unraisablehook", self.background.unraisable_error),
                      patch.object(tk.Tk, "report_callback_exception",
                                   lambda root, *args: self.background.tk_error(root, *args))]
        for hook in self.hooks:
            hook.start()
        faulthandler.dump_traceback_later(30, repeat=True)
        super().startTest(test)

    def addSuccess(self, test):
        # Defer success until teardown/GC and background exception checks finish.
        self.pending_success = test

    def stopTest(self, test):
        gc.collect()
        faulthandler.cancel_dump_traceback_later()
        changed = sorted(key for key in set(self.environment) | set(os.environ)
                         if self.environment.get(key) != os.environ.get(key))
        if changed:
            self.background.errors.append("测试未恢复环境变量：" + ", ".join(changed))
            os.environ.clear()
            os.environ.update(self.environment)
        for hook in reversed(self.hooks):
            hook.stop()
        if self.background.errors:
            try:
                raise AssertionError("\n".join(self.background.errors))
            except AssertionError:
                self.addFailure(test, sys.exc_info())
        elif getattr(self, "pending_success", None) is test:
            super().addSuccess(test)
        self.pending_success = None
        super().stopTest(test)


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order", choices=("normal", "reverse", "shuffle"), default="normal")
    parser.add_argument("--seed", type=int, default=20261110)
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()
    loader = unittest.defaultTestLoader
    suite = loader.loadTestsFromNames(args.names) if args.names else loader.discover("tests/unit")
    cases = sorted(flatten(suite), key=lambda test: test.id(), reverse=args.order == "reverse")
    if args.order == "shuffle":
        random.Random(args.seed).shuffle(cases)
    result = unittest.TextTestRunner(verbosity=2, resultclass=StrictResult).run(unittest.TestSuite(cases))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
