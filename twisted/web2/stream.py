# -*- test-case-name: twisted.web2.test.test_stream -*-

"""
The stream module provides a simple abstraction of streaming
data. While Twisted already has some provisions for handling this in
its Producer/Consumer model, the rather complex interactions between
producer and consumer makes it difficult to implement something like
the CompoundStream object. Thus, this API.

The IStream interface is very simple. It consists of two methods:
read, and close. The read method should either return some data, None
if there is no data left to read, or a Deferred. Close frees up any
underlying resources and causes read to return None forevermore.

IByteStream adds a bit more to the API:
1) read is required to return objects conforming to the buffer interface.  
2) .length, which may either an integer number of bytes remaining, or
None if unknown
3) .split(position). Split takes a position, and splits the
stream in two pieces, returning the two new streams. Using the
original stream after calling split is not allowed. 

There are two builtin source stream classes: FileStream and
MemoryStream. The first produces data from a file object, the second
from a buffer in memory. Any number of these can be combined into one
stream with the CompoundStream object. Then, to interface with other
parts of Twisted, there are two transcievers: StreamProducer and
ProducerStream. The first takes a stream and turns it into an
IPushProducer, which will write to a consumer. The second is a
consumer which is a stream, so that other producers can write to it.
"""

from __future__ import generators

import copy, os, types
from zope.interface import Interface, Attribute, implements
from twisted.internet.defer import Deferred
from twisted.internet import interfaces as ti_interfaces, defer, reactor, protocol, error
from twisted.python import components
from twisted.python.failure import Failure

try:
    import mmap
except ImportError:
    mmap = None


class IStream(Interface):
    """A stream of arbitrary data."""
    
    def read():
        """Read some data.

        Returns some object representing the data.
        If there is no more data available, returns None.
        Can also return a Deferred resulting in one of the above.

        Errors may be indicated by exception or by a Deferred of a Failure.
        """
        
    def close():
        """Prematurely close. Should also cause further reads to
        return None."""

class IByteStream(IStream):
    """A stream which is of bytes."""
    
    length = Attribute("""How much data is in this stream. Can be None if unknown.""")
    
    def read():
        """Read some data.
        
        Returns an object conforming to the buffer interface, or
        if there is no more data available, returns None.
        Can also return a Deferred resulting in one of the above.

        Errors may be indicated by exception or by a Deferred of a Failure.
        """
    def split(point):
        """Split this stream into two, at byte position 'point'.

        Returns a tuple of (before, after). After calling split,
        no other methods should be called on this stream. Doing
        so will have undefined behavior.

        Implementation note:
        If you cannot implement split easily, you may implement it as:
          return fallbackSplit(self, point)
        """

    def close():
        """Prematurely close this stream. Should also cause further reads to
        return None. Additionally, .length should be set to 0.
        """

class ISendfileableStream(Interface):
    def read(sendfile=False):
        """
        Read some data.
        If sendfile == False, returns an object conforming to the buffer
        interface, or else a Deferred.

        If sendfile == True, returns either the above, or a SendfileBuffer.
        """
        
class SimpleStream:
    """Superclass of simple streams with a single buffer and a offset and length
    into that buffer."""
    implements(IByteStream)
    
    length = None
    start = None
    
    def read(self):
        return None

    def close(self):
        self.length = 0
    
    def split(self, point):
        if self.length is not None:
            if point > self.length:
                raise ValueError("split point (%d) > length (%d)" % (point, self.length))
        b = copy.copy(self)
        self.length = point
        if b.length is not None:
            b.length -= point
        b.start += point
        return (self, b)
        
# maximum mmap size
MMAP_LIMIT = 4*1024*1024
# minimum mmap size
MMAP_THRESHOLD = 8*1024

# maximum sendfile length
SENDFILE_LIMIT = 16777216
# minimum sendfile size
SENDFILE_THRESHOLD = 256

def mmapwrapper(*args, **kwargs):
    """
    Python's mmap call sucks and ommitted the "offset" argument for no
    discernable reason. Replace this with a mmap module that has offset.
    """
    
    offset = kwargs.get('offset', None)
    if offset == 0:
        del kwargs['offset']
    else:
        raise mmap.error("mmap: Python sucks and does not support offset.")
    return mmap.mmap(*args, **kwargs)

class FileStream(SimpleStream):
    implements(ISendfileableStream)
    """A stream that reads data from a file. File must be a normal
    file that supports seek, (e.g. not a pipe or device or socket)."""
    # 65K, minus some slack
    CHUNK_SIZE = 2 ** 2 ** 2 ** 2 - 32

    f = None
    def __init__(self, f, start=0, length=None, useMMap=bool(mmap)):
        """
        Create the stream from file f. If you specify start and length,
        use only that portion of the file.
        """
        self.f = f
        self.start = start
        if length is None:
            self.length = os.fstat(f.fileno()).st_size
        else:
            self.length = length
        self.useMMap = useMMap
        
    def read(self, sendfile=False):
        if self.f is None:
            return None

        length = self.length
        if length == 0:
            self.f = None
            return None

        if sendfile and length > SENDFILE_THRESHOLD:
            # XXX: Yay using non-existent sendfile support!
            # FIXME: if we return a SendfileBuffer, and then sendfile
            #        fails, then what? Or, what if file is too short?
            readSize = min(length, SENDFILE_LIMIT)
            res = SendfileBuffer(self.f, self.start, readSize)
            self.length -= readSize
            self.start += readSize
            return res

        if self.useMMap and length > MMAP_THRESHOLD:
            readSize = min(length, MMAP_LIMIT)
            try:
                res = mmapwrapper(self.f.fileno(), readSize,
                                  access=mmap.ACCESS_READ, offset=self.start)
                #madvise(res, MADV_SEQUENTIAL)
                self.length -= readSize
                self.start += readSize
                return res
            except mmap.error:
                pass

        # Fall back to standard read.
        readSize = min(length, self.CHUNK_SIZE)

        self.f.seek(self.start)
        b = self.f.read(readSize)
        bytesRead = len(b)
        if not bytesRead:
            raise RuntimeError("Ran out of data reading file %r, expected %d more bytes" % (self.f, length))
        else:
            self.length -= bytesRead
            self.start += bytesRead
            return b

    def close(self):
        self.f = None
        SimpleStream.close(self)

components.registerAdapter(FileStream, file, IByteStream)


class MemoryStream(SimpleStream):
    """A stream that reads data from a buffer object."""
    def __init__(self, mem, start=0, length=None):
        """
        Create the stream from buffer object mem. If you specify start and length,
        use only that portion of the buffer.
        """
        self.mem = mem
        self.start = start
        if length is None:
            self.length = len(mem) - start
        else:
            if len(mem) < length:
                raise ValueError("len(mem) < start + length")
            self.length = length

    def read(self):
        if self.mem is None:
            return None
        if self.length == 0:
            result = None
        else:
            result = buffer(self.mem, self.start, self.length)
        self.mem = None
        self.length = 0
        return result

    def close(self):
        self.mem = None
        SimpleStream.close(self)

components.registerAdapter(MemoryStream, str, IByteStream)
components.registerAdapter(MemoryStream, types.BufferType, IByteStream)


class CompoundStream:
    """A stream which is composed of many other streams.

    Call addStream to add substreams.
    """
    
    implements(IByteStream, ISendfileableStream)
    deferred = None
    length = 0
    
    def __init__(self, buckets=()):
        self.buckets = [IByteStream(s) for s in buckets]
        
    def addStream(self, bucket):
        """Add a stream to the output"""
        bucket = IByteStream(bucket)
        self.buckets.append(bucket)
        if self.length is not None:
            if bucket.length is None:
                self.length = None
            else:
                self.length += bucket.length

    def read(self, sendfile=False):
        if self.deferred is not None:
            raise RuntimeError("Call to read while read is already outstanding")

        if not self.buckets:
            return None
        
        if sendfile and ISendfileableStream.providedBy(self.buckets[0]):
            result = self.buckets[0].read(sendfile)
        else:
            result = self.buckets[0].read()
        
        if isinstance(result, Deferred):
            self.deferred = result
            result.addCallback(self._gotRead, sendfile)
            return result
        
        return self._gotRead(result, sendfile)
        
    def _gotRead(self, result, sendfile):
        if result is None:
            del self.buckets[0]
            # Next bucket
            return self.read(sendfile)
        
        if self.length is not None:
            self.length -= len(result)
        self.deferred = None
        return result
    
    def split(self, point):
        num = 0
        origPoint = point
        for bucket in self.buckets:
            num+=1

            if point == 0:
                b = CompoundStream()
                b.buckets = self.buckets[num:]
                del self.buckets[num:]
                return self,b
            
            if bucket.length is None:
                # Indeterminate length bucket.
                # give up and use fallback splitter.
                return fallbackSplit(self, origPoint)
            
            if point < bucket.length:
                before,after = bucket.split(point)
                b = CompoundStream()
                b.buckets = self.buckets[num:]
                b.buckets[0] = after
                
                del self.buckets[num+1:]
                self.buckets[num] = before
                return self,b
            
            point -= bucket.length
    
    def close(self):
        for bucket in self.buckets:
            bucket.close()
        self.buckets = []
        self.length = 0



class _StreamReader:
    """Process a stream's data using callbacks for data and stream finish."""

    def __init__(self, stream, gotDataCallback):
        self.stream = stream
        self.gotDataCallback = gotDataCallback
        self.result = Deferred()

    def run(self):
        # self.result may be del'd in _read()
        result = self.result
        self._read()
        return result
    
    def _read(self):
        try:
            result = self.stream.read()
        except:
            self._gotError(Failure())
            return
        if isinstance(result, Deferred):
            result.addCallbacks(self._gotData, self._gotError)
        else:
            self._gotData(result)

    def _gotError(self, failure):
        self.result.errback(failure)
        del self.result
    
    def _gotData(self, data):
        if data is None:
            self.result.callback(None)
            del self.result
            return
        try:
            self.gotDataCallback(data)
        except:
            self._gotError(Failure())
            return
        reactor.callLater(0, self._read)

def readStream(stream, gotDataCallback):
    """Pass a stream's data to a callback.

    Returns Deferred which will be triggered on finish.  Errors in
    reading the stream or in processing it will be returned via this
    Deferred.
    """
    return _StreamReader(stream, gotDataCallback).run()


def readAndDiscard(stream):
    """Read all the data from the given stream, and throw it out.

    Returns Deferred which will be triggered on finish.
    """
    return readStream(stream, lambda _: None)

def readIntoFile(stream, outFile):
    """Read a stream and write it into a file.

    Returns Deferred which will be triggered on finish.
    """
    def done(_):
        outFile.close()
        return _
    return readStream(stream, outFile.write).addBoth(done)


def fallbackSplit(stream, point):
    after = PostTruncaterStream(stream, point)
    before = TruncaterStream(stream, point, after)
    return (before, after)

class TruncaterStream:
    def __init__(self, stream, point, postTruncater):
        self.stream = stream
        self.length = point
        self.postTruncater = postTruncater
        
    def read(self):
        if self.length == 0:
            if self.postTruncater is not None:
                postTruncater = self.postTruncater
                self.postTruncater = None
                postTruncater.sendInitialSegment(self.stream.read())
            self.stream = None
            return None
        
        result = self.stream.read()
        if isinstance(result, Deferred):
            return result.addCallback(self._gotRead)
        else:
            return self._gotRead(result)
        
    def _gotRead(self, data):
        if data is None:
            raise ValueError("Ran out of data for a split of a indeterminate length source")
        if self.length >= len(data):
            self.length -= len(data)
            return data
        else:
            before = buffer(data, 0, self.length)
            after = buffer(data, self.length)
            self.length = 0
            if self.postTruncater is not None:
                postTruncater = self.postTruncater
                self.postTruncater = None
                postTruncater.sendInitialSegment(after)
                self.stream = None
            return before
    
    def split(self, point):
        if point > self.length:
            raise ValueError("split point (%d) > length (%d)" % (point, self.length))

        post = PostTruncaterStream(self.stream, point)
        trunc = TruncaterStream(post, self.length - point, self.postTruncater)
        self.length = point
        self.postTruncater = post
        return self, trunc
    
    def close(self):
        if self.postTruncater is not None:
            self.postTruncater.notifyClosed(self)
        else:
            # Nothing cares about the rest of the stream
            self.stream.close()
            self.stream = None
            self.length = 0
            

class PostTruncaterStream:
    deferred = None
    sentInitialSegment = False
    truncaterClosed = None
    closed = False
    
    length = None
    def __init__(self, stream, point):
        self.stream = stream
        self.deferred = Deferred()
        if stream.length is not None:
            self.length = stream.length - point

    def read(self):
        if not self.sentInitialSegment:
            self.sentInitialSegment = True
            if self.truncaterClosed is not None:
                readAndDiscard(self.truncaterClosed)
                self.truncaterClosed = None
            return self.deferred
        
        return self.stream.read()
    
    def split(self, point):
        return fallbackSplit(self, point)
        
    def close(self):
        self.closed = True
        if self.truncaterClosed is not None:
            # have first half close itself
            self.truncaterClosed.postTruncater = None
            self.truncaterClosed.close()
        elif self.sentInitialSegment:
            # first half already finished up
            self.stream.close()
            
        self.deferred = None
    
    # Callbacks from TruncaterStream
    def sendInitialSegment(self, data):
        if self.closed:
            # First half finished, we don't want data.
            self.stream.close()
            self.stream = None
        if self.deferred is not None:
            if isinstance(data, Deferred):
                data.chainDeferred(self.deferred)
            else:
                self.deferred.callback(data)
        
    def notifyClosed(self, truncater):
        if self.closed:
            # we are closed, have first half really close
            truncater.postTruncater = None
            truncater.close()
        elif self.sentInitialSegment:
            # We are trying to read, read up first half
            readAndDiscard(truncater)
        else:
            # Idle, store closed info.
            self.truncaterClosed = truncater

            
class ProducerStream:
    """Turns producers into a IByteStream.
    Thus, implements IConsumer and IByteStream."""

    implements(IByteStream, ti_interfaces.IConsumer)
    length = None
    closed = False
    failed = False
    producer = None
    producerPaused = False
    deferred = None
    
    bufferSize = 5
    
    def __init__(self, length=None):
        self.buffer = []
        self.length = length
        
    # IByteStream implementation
    def read(self):
        if self.buffer:
            return self.buffer.pop(0)
        elif self.closed:
            self.length = 0
            if self.failed:
                f = self.failure
                del self.failure
                return defer.fail(f)
            return None
        else:
            deferred = self.deferred = Deferred()
            if self.producer is not None and (not self.streamingProducer
                                              or self.producerPaused):
                self.producerPaused = False
                self.producer.resumeProducing()
                
            return deferred
        
    def split(self, point):
        return fallbackSplit(self, point)
    
    def close(self):
        """Called by reader of stream when it is done reading."""
        self.buffer=[]
        self.closed = True
        if self.producer is not None:
            self.producer.stopProducing()
            self.producer = None
        self.deferred = None
        
    # IConsumer implementation
    def write(self, data):
        if self.closed:
            return
        
        if self.deferred:
            deferred = self.deferred
            self.deferred = None
            deferred.callback(data)
        else:
            self.buffer.append(data)
            if(self.producer is not None and self.streamingProducer
               and len(self.buffer) > self.bufferSize):
                self.producer.pauseProducing()
                self.producerPaused = True

    def finish(self, failure=None):
        """Called by producer when it is done.

        If the optional failure argument is passed a Failure instance,
        the stream will return it as errback on next Deferred.
        """
        self.closed = True
        if not self.buffer:
            self.length = 0
        if self.deferred is not None:
            deferred = self.deferred
            self.deferred = None
            if failure is not None:
                self.failed = True
                deferred.errback(failure)
            else:
                deferred.callback(None)
        else:
            if failure is not None:
               self.failed = True
               self.failure = failure
    
    def registerProducer(self, producer, streaming):
        if self.producer is not None:
            raise RuntimeError("Cannot register producer %s, because producer %s was never unregistered." % (producer, self.producer))
        
        if self.closed:
            producer.stopProducing()
        else:
            self.producer = producer
            self.streamingProducer = streaming
            if not streaming:
                producer.resumeProducing()

    def unregisterProducer(self):
        self.producer = None
        
class StreamProducer:
    """A push producer which gets its data by reading a stream."""
    implements(ti_interfaces.IPushProducer)

    deferred = None
    finishedCallback = None
    paused = False
    consumer = None
    
    def __init__(self, stream, enforceStr=True):
        self.stream = stream
        self.enforceStr = enforceStr
        
    def beginProducing(self, consumer):
        if self.stream is None:
            return defer.succeed(None)
        
        self.consumer = consumer
        finishedCallback = self.finishedCallback = Deferred()
        self.consumer.registerProducer(self, True)
        self.resumeProducing()
        return finishedCallback
    
    def resumeProducing(self):
        self.paused = False
        if self.deferred is not None:
            return
        
        data = self.stream.read()
        
        if isinstance(data, Deferred):
            # FIXME: what about errback?
            self.deferred = data.addCallback(self._doWrite)
        else:
            self._doWrite(data)

    def _doWrite(self, data):
        if self.consumer is None:
            return
        if data is None:
            # The end.
            self.consumer.unregisterProducer()
            self.finishedCallback.callback(None)
            self.finishedCallback = self.deferred = self.consumer = self.stream = None
            return
        
        self.deferred = None
        if self.enforceStr:
            # XXX: sucks that we have to do this. make transport.write(buffer) work!
            data = str(buffer(data))
        self.consumer.write(data)
        
        if not self.paused:
            self.resumeProducing()
        
    def pauseProducing(self):
        self.paused = True

    def stopProducing(self):
        if self.consumer is not None:
            self.consumer.unregisterProducer()
        if self.finishedCallback is not None:
            from twisted.internet import main
            self.finishedCallback.errback(main.CONNECTION_LOST)
        self.paused = True
        if self.stream is not None:
            self.stream.close()
            
        self.finishedCallback = self.deferred = self.consumer = self.stream = None


class _ProcessStreamerProtocol(protocol.ProcessProtocol):

    def __init__(self, inputStream, outStream, errStream):
        self.inputStream = inputStream
        self.outStream = outStream
        self.errStream = errStream
        self.resultDeferred = defer.Deferred()
    
    def connectionMade(self):
        p = StreamProducer(self.inputStream)
        d = p.beginProducing(self.transport)
        d.addCallback(lambda _: self.transport.closeStdin())

    def outReceived(self, data):
        self.outStream.write(data)

    def errReceived(self, data):
        self.errStream.write(data)

    def outConnectionLost(self):
        self.outStream.finish()

    def errConnectionLost(self):
        self.errStream.finish()
    
    def processEnded(self, reason):
        self.resultDeferred.errback(reason)
        del self.resultDeferred


class ProcessStreamer:
    """Runs a process hooked up to streams.

    Requires an input stream, has attributes 'outStream' and 'errStream'
    for stdout and stderr.

    outStream and errStream are public attributes providing streams
    for stdout and stderr of the process.
    """

    def __init__(self, inputStream, program, args, env={}):
        self.outStream = ProducerStream()
        self.errStream = ProducerStream()
        self._protocol = _ProcessStreamerProtocol(IByteStream(inputStream), self.outStream, self.errStream)
        self._program = program
        self._args = args
        self._env = env
    
    def run(self):
        """Run the process.

        Returns Deferred which will eventually have errback for non-clean (exit code > 0)
        exit, with ProcessTerminated, or callback with None on exit code 0.
        """
        # XXX what happens if spawn fails?
        reactor.spawnProcess(self._protocol, self._program, self._args, env=self._env)
        del self._env
        return self._protocol.resultDeferred.addErrback(lambda _: _.trap(error.ProcessDone))

    def getPID(self):
        """Return the PID of the process."""
        return self._protocol.transport.pid


class BufferedStream(object):
    """A stream which buffers its data to provide operations like
    readline and readExactly."""
    
    data = ""
    def __init__(self, stream):
        self.stream = stream

    def _readUntil(self, f):
        """Internal helper function which repeatedly calls f each time
        after more data has been received, until it returns non-None."""
        while True:
            r = f()
            if r is not None:
                yield r; return
            
            newdata = self.stream.read()
            if isinstance(newdata, defer.Deferred):
                newdata = defer.waitForDeferred(newdata)
                yield newdata; newdata = newdata.getResult()
            
            if not newdata:
                # End Of File
                newdata = self.data
                self.data = ''
                yield newdata; return
            self.data += str(newdata)
    _readUntil = defer.deferredGenerator(_readUntil)

    def readExactly(self, size=None):
        """Read exactly size bytes of data, or, if size is None, read
        the entire stream into a string."""
        def gotdata():
            data = self.data
            if size is not None and len(data) >= size:
                pre,post = data[:size], data[size:]
                self.data=post
                return pre
        return self._readUntil(gotdata)
    
        
    def readline(self, delimiter='\r\n'):
        """Read a line of data from the string, bounded by delimiter"""
        def gotdata():
            data = self.data.split(delimiter, 1)
            if len(data) == 2:
                self.data=data[1]
                return data[0]
        return self._readUntil(gotdata)

    def pushback(self, pushed):
        """Push data back into the buffer."""
        
        self.data = pushed + self.data
        
    def read(self):
        data = self.data
        if data:
            self.data = ""
            return data
        return self.stream.read()

    def _len(self):
        l = self.stream.length
        if l is None:
            return None
        return l + len(self.data)
    
    length = property(_len)
    
    def split(self, offset):
        off = offset - len(self.data)
        
        pre, post = self.stream.split(max(0, off))
        pre = BufferedStream(pre)
        post = BufferedStream(post)
        if off < 0:
            pre.data = self.data[:-off]
            post.data = self.data[-off:]
        else:
            pre.data = self.data
        
        return pre, post

__all__ = ['IStream', 'IByteStream', 'FileStream', 'MemoryStream', 'CompoundStream',
           'readAndDiscard', 'fallbackSplit', 'ProducerStream', 'StreamProducer',
           'BufferedStream', 'readStream', 'ProcessStreamer', 'readIntoFile']

