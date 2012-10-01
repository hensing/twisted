# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.

"""
Provide lists of modules ported to Python 3.

Modules listed below have been ported to Python 3. The port may be partial,
with only some functionality available.

run-python3-tests uses this, and in the future it may be used by setup.py and
pydoctor.
"""

from __future__ import division, absolute_import

# A list of modules that have been ported, e.g. "twisted.python.versions"; a
# package name (e.g. "twisted.python") indicates the corresponding __init__.py
# file has been ported (e.g. "twisted/python/__init__.py"). To reduce merge
# conflicts, add new lines in alphabetical sort.
modules = [
    "twisted",
    "twisted.internet",
    "twisted.internet.address",
    "twisted.internet.default",
    "twisted.internet.defer",
    "twisted.internet.error",
    "twisted.internet.interfaces",
    "twisted.internet.fdesc",
    "twisted.internet.main",
    "twisted.internet.reactor", # don't expect it to work yet, though!
    "twisted.internet._signals",
    "twisted.internet.test",
    "twisted.internet.test.modulehelpers",
    "twisted.internet.test.reactormixins",
    "twisted.internet._utilspy3",
    "twisted.python",
    "twisted.python.compat",
    "twisted.python.components",
    "twisted.python.context",
    "twisted.python._deprecatepy3",
    "twisted.python.failure",
    # filepaths depends on twisted.python.win32 which hasn't yet been ported,
    # but works well enough to be imported:
    "twisted.python.filepath",
    "twisted.python.log",
    "twisted.python.monkey",
    "twisted.python._reflectpy3",
    "twisted.python.runtime",
    "twisted.python.test",
    "twisted.python.threadable",
    "twisted.python.threadpool",
    "twisted.python._utilpy3",
    "twisted.python.versions",
    "twisted.test",
    "twisted.trial",
    "twisted.trial.itrial",
    "twisted.trial._synctest",
    "twisted.trial.test",
    "twisted.trial.test.suppression",
    "twisted.trial.test.packages",
    "twisted.trial.unittest",
    "twisted.trial.util",
    "twisted.trial._utilpy3",
    "twisted._version",
    ]


# A list of test modules that have been ported, e.g
# "twisted.python.test.test_versions". To reduce merge conflicts, add new
# lines in alphabetical sort.
testModules = [
    "twisted.internet.test.test_abstract",
    "twisted.internet.test.test_address",
    "twisted.internet.test.test_default",
    "twisted.internet.test.test_fdset",
    "twisted.internet.test.test_filedescriptor",
    "twisted.internet.test.test_main",
    "twisted.internet.test.test_sigchld",
    "twisted.internet.test.test_threads",
    "twisted.internet.test.test_udp",
    "twisted.internet.test.test_udp_internals",
    "twisted.internet.test.test_utilspy3",
    "twisted.python.test.test_components",
    "twisted.python.test.test_deprecatepy3",
    "twisted.python.test.test_reflectpy3",
    "twisted.python.test.test_runtime",
    "twisted.python.test.test_utilpy3",
    "twisted.python.test.test_versions",
    "twisted.test.test_compat",
    "twisted.test.test_context",
    "twisted.test.test_defer",
    "twisted.test.test_error",
    "twisted.test.test_failure",
    "twisted.test.test_fdesc",
    "twisted.test.test_log",
    "twisted.test.test_monkey",
    "twisted.test.test_paths",
    "twisted.test.test_threadable",
    "twisted.test.test_twisted",
    "twisted.test.test_threadpool",
    "twisted.trial.test.test_assertions",
    "twisted.trial.test.test_pyunitcompat",
    "twisted.trial.test.test_suppression",
    "twisted.trial.test.test_utilpy3",
    "twisted.trial.test.test_util",
    "twisted.trial.test.test_warning",
    ]
