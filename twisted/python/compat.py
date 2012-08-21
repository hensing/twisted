# -*- test-case-name: twisted.test.test_compat -*-
#
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""
Compatibility module to provide backwards compatibility for useful Python
features.

This is mainly for use of internal Twisted code. We encourage you to use
the latest version of Python directly from your code, if possible.
"""

from __future__ import division

import sys, string, socket, struct


if sys.version_info < (3, 0):
    _PY3 = False
else:
    _PY3 = True



def inet_pton(af, addr):
    if af == socket.AF_INET:
        return socket.inet_aton(addr)
    elif af == getattr(socket, 'AF_INET6', 'AF_INET6'):
        if [x for x in addr if x not in string.hexdigits + ':.']:
            raise ValueError("Illegal characters: %r" % (''.join(x),))

        parts = addr.split(':')
        elided = parts.count('')
        ipv4Component = '.' in parts[-1]

        if len(parts) > (8 - ipv4Component) or elided > 3:
            raise ValueError("Syntactically invalid address")

        if elided == 3:
            return '\x00' * 16

        if elided:
            zeros = ['0'] * (8 - len(parts) - ipv4Component + elided)

            if addr.startswith('::'):
                parts[:2] = zeros
            elif addr.endswith('::'):
                parts[-2:] = zeros
            else:
                idx = parts.index('')
                parts[idx:idx+1] = zeros

            if len(parts) != 8 - ipv4Component:
                raise ValueError("Syntactically invalid address")
        else:
            if len(parts) != (8 - ipv4Component):
                raise ValueError("Syntactically invalid address")

        if ipv4Component:
            if parts[-1].count('.') != 3:
                raise ValueError("Syntactically invalid address")
            rawipv4 = socket.inet_aton(parts[-1])
            unpackedipv4 = struct.unpack('!HH', rawipv4)
            parts[-1:] = [hex(x)[2:] for x in unpackedipv4]

        parts = [int(x, 16) for x in parts]
        return struct.pack('!8H', *parts)
    else:
        raise socket.error(97, 'Address family not supported by protocol')

def inet_ntop(af, addr):
    if af == socket.AF_INET:
        return socket.inet_ntoa(addr)
    elif af == socket.AF_INET6:
        if len(addr) != 16:
            raise ValueError("address length incorrect")
        parts = struct.unpack('!8H', addr)
        curBase = bestBase = None
        for i in range(8):
            if not parts[i]:
                if curBase is None:
                    curBase = i
                    curLen = 0
                curLen += 1
            else:
                if curBase is not None:
                    if bestBase is None or curLen > bestLen:
                        bestBase = curBase
                        bestLen = curLen
                    curBase = None
        if curBase is not None and (bestBase is None or curLen > bestLen):
            bestBase = curBase
            bestLen = curLen
        parts = [hex(x)[2:] for x in parts]
        if bestBase is not None:
            parts[bestBase:bestBase + bestLen] = ['']
        if parts[0] == '':
            parts.insert(0, '')
        if parts[-1] == '':
            parts.insert(len(parts) - 1, '')
        return ':'.join(parts)
    else:
        raise socket.error(97, 'Address family not supported by protocol')

try:
    socket.AF_INET6
except AttributeError:
    socket.AF_INET6 = 'AF_INET6'

try:
    socket.inet_pton(socket.AF_INET6, "::")
except (AttributeError, NameError, socket.error):
    socket.inet_pton = inet_pton
    socket.inet_ntop = inet_ntop


adict = dict



if _PY3:
    # These are actually useless in Python 2 as well, but we need to go
    # through deprecation process there (ticket #5895):
    del adict, inet_pton, inet_ntop



# OpenSSL/__init__.py imports OpenSSL.tsafe.  OpenSSL/tsafe.py imports
# threading.  threading imports thread.  All to make this stupid threadsafe
# version of its Connection class.  We don't even care about threadsafe
# Connections.  In the interest of not screwing over some crazy person
# calling into OpenSSL from another thread and trying to use Twisted's SSL
# support, we don't totally destroy OpenSSL.tsafe, but we will replace it
# with our own version which imports threading as late as possible.

class tsafe(object):
    class Connection:
        """
        OpenSSL.tsafe.Connection, defined in such a way as to not blow.
        """
        __module__ = 'OpenSSL.tsafe'

        def __init__(self, *args):
            from OpenSSL import SSL as _ssl
            self._ssl_conn = apply(_ssl.Connection, args)
            from threading import _RLock
            self._lock = _RLock()

        for f in ('get_context', 'pending', 'send', 'write', 'recv',
                  'read', 'renegotiate', 'bind', 'listen', 'connect',
                  'accept', 'setblocking', 'fileno', 'shutdown',
                  'close', 'get_cipher_list', 'getpeername',
                  'getsockname', 'getsockopt', 'setsockopt',
                  'makefile', 'get_app_data', 'set_app_data',
                  'state_string', 'sock_shutdown',
                  'get_peer_certificate', 'want_read', 'want_write',
                  'set_connect_state', 'set_accept_state',
                  'connect_ex', 'sendall'):

            exec("""def %s(self, *args):
                self._lock.acquire()
                try:
                    return apply(self._ssl_conn.%s, args)
                finally:
                    self._lock.release()\n""" % (f, f))
sys.modules['OpenSSL.tsafe'] = tsafe



try:
    set = set
except NameError:
    from sets import Set as set


try:
    frozenset = frozenset
except NameError:
    from sets import ImmutableSet as frozenset


try:
    from functools import reduce
except ImportError:
    reduce = reduce



def execfile(filename, globals, locals=None):
    """
    Execute a Python script in the given namespaces.

    Similar to the execfile builtin, but a namespace is mandatory, partly
    because that's a sensible thing to require, and because otherwise we'd
    have to do some frame hacking.

    This is a compatibility implementation for Python 3 porting, to avoid the
    use of the deprecated builtin C{execfile} function.
    """
    if locals is None:
        locals = globals
    fin = open(filename, "rbU")
    try:
        source = fin.read()
    finally:
        fin.close()
    code = compile(source, filename, "exec")
    exec(code, globals, locals)


try:
    cmp = cmp
except NameError:
    def cmp(a, b):
        """
        Compare two objects.

        Returns a negative number if C{a < b}, zero if they are equal, and a
        positive number if C{a > b}.
        """
        if a < b:
            return -1
        elif a == b:
            return 0
        else:
            return 1



def comparable(klass):
    """
    Class decorator that ensures support for the special C{__cmp__} method.

    On Python 2 this does nothing.

    On Python 3, C{__eq__}, C{__lt__}, etc. methods are added to the class,
    relying on C{__cmp__} to implement their comparisons.
    """
    # On Python 2, __cmp__ will just work, so no need to add extra methods:
    if not _PY3:
        return klass

    def __eq__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c == 0


    def __ne__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c != 0


    def __lt__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c < 0


    def __le__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c <= 0


    def __gt__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c > 0


    def __ge__(self, other):
        c = self.__cmp__(other)
        if c is NotImplemented:
            return c
        return c >= 0

    klass.__lt__ = __lt__
    klass.__gt__ = __gt__
    klass.__le__ = __le__
    klass.__ge__ = __ge__
    klass.__eq__ = __eq__
    klass.__ne__ = __ne__
    return klass



__all__ = [
    "execfile",
    "frozenset",
    "reduce",
    "set",
    "cmp",
    "comparable",
    ]
