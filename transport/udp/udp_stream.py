#!/usr/bin/env python
# udp_stream.py
#
# Copyright (C) 2008-2016 Veselin Penev, http://bitdust.io
#
# This file (udp_stream.py) is part of BitDust Software.
#
# BitDust is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# BitDust Software is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with BitDust Software.  If not, see <http://www.gnu.org/licenses/>.
#
# Please contact us if you have any questions at bitdust.io@gmail.com

"""
.. module:: udp_stream.

.. role:: red

BitDust udp_stream() Automat

.. raw:: html

    <a href="udp_stream.png" target="_blank">
    <img src="udp_stream.png" style="max-width:100%;">
    </a>

EVENTS:
    * :red:`ack-received`
    * :red:`block-received`
    * :red:`close`
    * :red:`consume`
    * :red:`init`
    * :red:`iterate`
    * :red:`resume`
    * :red:`set-limits`
    * :red:`timeout`
"""

"""
TODO: Need to put small explanation here.

Datagrams format:

    DATA packet:

        bytes:
          0        software version number
          1        command identifier, see ``lib.udp`` module
          2-5      stream_id
          6-9      total data size to be transferred,
                   peer must know when to stop receiving
          10-13    block_id, outgoing blocks are counted from 1
          from 14  payload data


    ACK packet:

        bytes:
          0        software version number
          1        command identifier, see ``lib.udp`` module
          2-5      stream_id
          6-9      block_id1
          10-13    block_id2
          14-17    block_id3
          ...


"""

#------------------------------------------------------------------------------

_Debug = True
_DebugLevel = 16

#------------------------------------------------------------------------------

import time
import cStringIO
import struct
import bisect
import random

from twisted.internet import reactor

from logs import lg

from lib import misc

from automats import automat

#------------------------------------------------------------------------------

POOLING_INTERVAL = 0.05  # smaller pooling size will increase CPU load
UDP_DATAGRAM_SIZE = 508  # largest safe datagram size
BLOCK_SIZE = UDP_DATAGRAM_SIZE - 14  # 14 bytes - BitDust header

BLOCKS_PER_ACK = 8  # need to verify delivery get success
# ack packets will be sent as response,
# one output ack per every N data blocks received

OUTPUT_BUFFER_SIZE = 16 * 1024  # how many bytes to read from file at once
CHUNK_SIZE = BLOCK_SIZE * BLOCKS_PER_ACK  # so we know how much to read now

RTT_MIN_LIMIT = 0.004  # round trip time, this adjust how fast we try to send
RTT_MAX_LIMIT = 3.0    # set ack response timeout for sending
MAX_RTT_COUNTER = 100  # used to calculate avarage RTT for this stream

RECEIVING_TIMEOUT = 10  # decide about the moment to kill the stream

MAX_BLOCKS_INTERVAL = 3  # resending blocks at lease every N seconds
MAX_ACK_TIMEOUTS = 5  # if we get too much errors - connection will be closed

# CHECK_ERRORS_INTERVAL = 20  # will verify sending errors every N iterations
ACCEPTABLE_ERRORS_RATE = 0.05  # 2% errors considered to be acceptable quality
SENDING_LIMIT_FACTOR_ON_START = 1.0  # 0.5  # start sending at half speed
# MIN_SENDING_LIMIT_FACTOR = 0.03125

#------------------------------------------------------------------------------

_Streams = {}
_ProcessStreamsTask = None
_ProcessStreamsIterations = 0

_GlobalLimitReceiveBytesPerSec = 1000.0 * 125000  # default receiveing limit bps
_GlobalLimitSendBytesPerSec = 1000.0 * 125000  # default sending limit bps
# start sending at half speed
# _CalculatedLimitSendBytesPerSec = _GlobalLimitSendBytesPerSec * SENDING_LIMIT_FACTOR_ON_START
_CurrentSendingAvarageRate = 0.0

#------------------------------------------------------------------------------

def streams():
    global _Streams
    return _Streams


def create(stream_id, consumer, producer):
    """
    Creates a new UDP stream.
    """
    if _Debug:
        lg.out(_DebugLevel - 6, 'udp_stream.create stream_id=%s' % str(stream_id))
    s = UDPStream(stream_id, consumer, producer)
    streams()[s.stream_id] = s
    s.automat('init')
    reactor.callLater(0, balance_streams_limits)
    return s


def close(stream_id):
    """
    Close existing UDP stream.
    """
    s = streams().get(stream_id, None)
    if s is None:
        lg.warn('stream %d not exist')
        return False
    s.automat('close')
    if _Debug:
        lg.out(
            _DebugLevel -
            6,
            'udp_stream.close send "close" to stream %s' %
            str(stream_id))
    return True

#------------------------------------------------------------------------------

def get_global_input_limit_bytes_per_sec():
    global _GlobalLimitReceiveBytesPerSec
    return _GlobalLimitReceiveBytesPerSec


def set_global_input_limit_bytes_per_sec(bps):
    global _GlobalLimitReceiveBytesPerSec
    _GlobalLimitReceiveBytesPerSec = bps
    balance_streams_limits()


def get_global_output_limit_bytes_per_sec():
    global _GlobalLimitSendBytesPerSec
    return _GlobalLimitSendBytesPerSec


# def get_calculated_output_limit_bytes_per_sec():
#     global _CalculatedLimitSendBytesPerSec
#     return _CalculatedLimitSendBytesPerSec


def set_global_output_limit_bytes_per_sec(bps):
    global _GlobalLimitSendBytesPerSec
    global _CalculatedLimitSendBytesPerSec
    _GlobalLimitSendBytesPerSec = bps
    # _CalculatedLimitSendBytesPerSec = _GlobalLimitSendBytesPerSec * 0.5
    balance_streams_limits()

#------------------------------------------------------------------------------

def balance_streams_limits():
    receive_limit_per_stream = float(get_global_input_limit_bytes_per_sec())
    send_limit_per_stream = float(get_global_output_limit_bytes_per_sec())
    # send_limit_per_stream = min(
    #     float(get_global_output_limit_bytes_per_sec()),
    #     float(get_calculated_output_limit_bytes_per_sec()))
    num_streams = len(streams())
    if num_streams > 0:
        receive_limit_per_stream /= float(num_streams)
        send_limit_per_stream /= float(num_streams)
    if _Debug:
        lg.out(_DebugLevel, 'udp_stream.balance_streams_limits in:%r out:%r total:%d' % (
            receive_limit_per_stream, send_limit_per_stream, num_streams))
    for s in streams().values():
        s.automat('set-limits', (receive_limit_per_stream, send_limit_per_stream))


# def check_sending_errors():
#     global _CalculatedLimitSendBytesPerSec
#     global _CurrentSendingErrorsRate
#     total_attempts = 0.0
#     total_errors = 0.0
#     for s in streams().values():
#         total_attempts += s.output_quality_counter
#         total_errors += s.output_blocks_errors_counter
#     if total_attempts < 100:
#         return
#     current_errors_rate = total_errors / (total_attempts + 1.0)
#     current_limit = _CalculatedLimitSendBytesPerSec
#     if current_errors_rate < ACCEPTABLE_ERRORS_RATE:
#         if current_errors_rate < _CurrentSendingErrorsRate:
#             _CalculatedLimitSendBytesPerSec *= 1.1
#             if _CalculatedLimitSendBytesPerSec > get_global_output_limit_bytes_per_sec():
#                 _CalculatedLimitSendBytesPerSec = get_global_output_limit_bytes_per_sec()
#             else:
#                 if _Debug:
#                     lg.out(_DebugLevel, 'udp_stream.check_sending_errors SPEED UP: %r, blocks:%d, errors:%d %r<%r' % (
#                         _CalculatedLimitSendBytesPerSec,
#                         total_attempts, total_errors,
#                         current_errors_rate, _CurrentSendingErrorsRate))
#     if current_errors_rate >= ACCEPTABLE_ERRORS_RATE:
#         if current_errors_rate > _CurrentSendingErrorsRate:
#             _CalculatedLimitSendBytesPerSec *= 0.9
#             if _Debug:
#                 lg.out(_DebugLevel, 'udp_stream.check_sending_errors SPEED DOWN: %r, blocks:%d, errors:%d %r>%r' % (
#                     _CalculatedLimitSendBytesPerSec,
#                     total_attempts, total_errors,
#                     current_errors_rate, _CurrentSendingErrorsRate))
#     _CurrentSendingErrorsRate = current_errors_rate
#     if current_limit != _CalculatedLimitSendBytesPerSec:
#         balance_streams_limits()

#------------------------------------------------------------------------------

def sort_method(stream_instance):
    if stream_instance.state == 'SENDING':
        return stream_instance.output_bytes_per_sec_current
    return stream_instance.input_bytes_per_sec_current

def process_streams():
    global _ProcessStreamsTask
    global _ProcessStreamsIterations
    global _CurrentSendingAvarageRate
    # sort streams by sending/receiving speed
    # slowest streams will go first

#     active_streams = sorted(streams().values(), key=sort_method, reverse=False)
#     for s in active_streams:
#         if s.state == 'SENDING' or s.state == 'RECEIVING':
#             s.event('iterate')

    for s in streams().values():
        if s.state == 'RECEIVING':
            s.event('iterate')

#     max_streams_per_iteration = int(len(streams()) * POOLING_INTERVAL) + 1
#     stream_ids = list(streams().keys())
#     streams_counter = 0
#     while stream_ids and streams_counter <= max_streams_per_iteration:
#         pos = int(random.random() * len(stream_ids))   # random.choice(stream_ids)
#         stream_id = stream_ids.pop(pos)
#         s = streams()[stream_id]
#         if s.state == 'SENDING':
#             s.event('iterate')
#             streams_counter += 1

    sending_streams_count = 0.0
    total_sending_rate = 0.0
    for s in streams().values():
        if s.state == 'SENDING':
            s.event('iterate')
            total_sending_rate += s.get_current_output_bytes_per_sec()
            sending_streams_count += 1.0

    if sending_streams_count > 0.0:
        _CurrentSendingAvarageRate = total_sending_rate / sending_streams_count
    else:
        _CurrentSendingAvarageRate = 0.0

    if _ProcessStreamsTask is None or _ProcessStreamsTask.called:
        _ProcessStreamsTask = reactor.callLater(
            POOLING_INTERVAL, process_streams)
#     _ProcessStreamsIterations += 1
#     if _ProcessStreamsIterations % CHECK_ERRORS_INTERVAL == 1:
#         check_sending_errors()


def stop_process_streams():
    global _ProcessStreamsTask
    if _ProcessStreamsTask:
        if _ProcessStreamsTask.active():
            _ProcessStreamsTask.cancel()
        _ProcessStreamsTask = None

#------------------------------------------------------------------------------

class BufferOverflow(Exception):
    pass

#------------------------------------------------------------------------------

class UDPStream(automat.Automat):
    """
    This class implements all the functionality of the ``udp_stream()`` state
    machine.
    """

    fast = True

    post = True

    def __init__(self, stream_id, consumer, producer):
        self.stream_id = stream_id
        self.consumer = consumer
        self.producer = producer
        self.started = time.time()
        self.consumer.set_stream_callback(self.on_consume)
        if _Debug:
            lg.out(_DebugLevel, 'udp_stream.__init__ %d peer_id:%s session:%s' % (
                self.stream_id, self.producer.session.peer_id, self.producer.session))
        name = 'udp_stream[%s]' % (self.stream_id)
        automat.Automat.__init__(self, name, 'AT_STARTUP',
                                 _DebugLevel, _Debug and lg.is_debug(_DebugLevel + 8))

    def __del__(self):
        if _Debug:
            lg.out(_DebugLevel, 'udp_stream.__del__ %d' % self.stream_id)
        automat.Automat.__del__(self)

    def init(self):
        self.output_acks_counter = 0
        self.output_acks_reasons = {}
        self.output_ack_last_time = 0
        self.output_block_id_current = 0
        self.output_acked_block_id_current = 0
        self.output_acked_blocks_ids = set()
        self.output_block_last_time = 0
        self.output_blocks = {}
        self.output_blocks_ids = []
        self.output_blocks_counter = 0
        self.output_blocks_reasons = {}
        self.output_blocks_acked = 0
        self.output_blocks_retries = 0
        self.output_blocks_lagged_counter = 0
        self.output_blocks_success_counter = 0.0
        self.output_blocks_timed_out_counter = 0
#         self.output_blocks_errors_counter = 0.0
        self.output_quality_counter = 0.0
        self.output_errors_last_time = 0.0
        self.output_bytes_in_acks = 0
        self.output_bytes_sent = 0
        self.output_bytes_sent_period = 0
        self.output_bytes_acked = 0
        self.output_bytes_per_sec_current = 0
        self.output_bytes_per_sec_last = 0
        self.output_buffer_size = 0
        self.output_limit_bytes_per_sec = 0
        self.output_limit_factor = SENDING_LIMIT_FACTOR_ON_START
        self.output_limit_bytes_per_sec_from_remote = -1
        self.output_rtt_avarage = 0.0
        self.output_rtt_counter = 1.0
        self.input_ack_last_time = 0
        self.input_ack_error_last_check = 0
        self.input_acks_counter = 0
        self.input_acks_timeouts_counter = 0
        self.input_acks_garbage_counter = 0
        self.input_blocks = {}
        self.input_block_id_current = 0
        self.input_block_last_time = 0
        self.input_block_id_last = 0
        self.input_blocks_counter = 0
        self.input_blocks_to_ack = []
        self.input_bytes_received = 0
        self.input_bytes_received_period = 0
        self.input_bytes_per_sec_current = 0
        self.input_duplicated_blocks = 0
        self.input_duplicated_bytes = 0
        self.input_old_blocks = 0
        self.input_limit_bytes_per_sec = 0
        self.last_progress_report = 0
        self.eof = False

    def A(self, event, arg):
        newstate = self.state
        #---SENDING---
        if self.state == 'SENDING':
            if event == 'iterate':
                self.doResendBlocks(arg)
                self.doSendingLoop(arg)
            elif event == 'consume':
                self.doPushBlocks(arg)
                self.doResendBlocks(arg)
                self.doSendingLoop(arg)
            elif event == 'set-limits':
                self.doUpdateLimits(arg)
            elif event == 'ack-received' and not self.isEOF(arg) and not self.isPaused(arg):
                pass
                # self.doResendBlocks(arg)
                # self.doSendingLoop(arg)
            elif event == 'ack-received' and self.isEOF(arg):
                self.doReportSendDone(arg)
                self.doCloseStream(arg)
                newstate = 'COMPLETION'
            elif event == 'ack-received' and self.isPaused(arg):
                self.doResumeLater(arg)
                newstate = 'PAUSE'
            elif event == 'timeout':
                self.doReportSendTimeout(arg)
                self.doCloseStream(arg)
                newstate = 'COMPLETION'
            elif event == 'close':
                self.doReportClosed(arg)
                self.doCloseStream(arg)
                self.doDestroyMe(arg)
                newstate = 'CLOSED'
        #---DOWNTIME---
        elif self.state == 'DOWNTIME':
            if event == 'set-limits':
                self.doUpdateLimits(arg)
            elif event == 'block-received':
                self.doResendAck(arg)
                self.doReceivingLoop(arg)
                newstate = 'RECEIVING'
            elif event == 'close':
                self.doReportClosed(arg)
                self.doCloseStream(arg)
                self.doDestroyMe(arg)
                newstate = 'CLOSED'
            elif event == 'ack-received':
                self.doReportError(arg)
                self.doCloseStream(arg)
                newstate = 'COMPLETION'
            elif event == 'consume':
                self.doPushBlocks(arg)
                self.doResendBlocks(arg)
                self.doSendingLoop(arg)
                newstate = 'SENDING'
        #---AT_STARTUP---
        elif self.state == 'AT_STARTUP':
            if event == 'init':
                self.doInit(arg)
                newstate = 'DOWNTIME'
        #---CLOSED---
        elif self.state == 'CLOSED':
            pass
        #---RECEIVING---
        elif self.state == 'RECEIVING':
            if event == 'set-limits':
                self.doUpdateLimits(arg)
            elif event == 'iterate':
                self.doResendAck(arg)
                self.doReceivingLoop(arg)
            elif event == 'block-received' and not self.isEOF(arg):
                self.doResendAck(arg)
                self.doReceivingLoop(arg)
            elif event == 'timeout':
                self.doReportReceiveTimeout(arg)
                self.doCloseStream(arg)
                newstate = 'COMPLETION'
            elif event == 'close':
                self.doReportClosed(arg)
                self.doCloseStream(arg)
                self.doDestroyMe(arg)
                newstate = 'CLOSED'
            elif event == 'block-received' and self.isEOF(arg):
                self.doResendAck(arg)
                self.doReportReceiveDone(arg)
                self.doCloseStream(arg)
                newstate = 'COMPLETION'
        #---COMPLETION---
        elif self.state == 'COMPLETION':
            if event == 'close':
                self.doDestroyMe(arg)
                newstate = 'CLOSED'
        #---PAUSE---
        elif self.state == 'PAUSE':
            if event == 'consume':
                self.doPushBlocks(arg)
            elif event == 'timeout':
                self.doReportSendTimeout(arg)
                self.doCloseStream(arg)
                newstate = 'COMPLETION'
            elif event == 'ack-received' and self.isEOF(arg):
                self.doReportSendDone(arg)
                self.doCloseStream(arg)
                newstate = 'COMPLETION'
            elif event == 'resume':
                self.doResendBlocks(arg)
                self.doSendingLoop(arg)
                newstate = 'SENDING'
            elif event == 'close':
                self.doReportClosed(arg)
                self.doCloseStream(arg)
                self.doDestroyMe(arg)
                newstate = 'CLOSED'
        return newstate

    def isEOF(self, arg):
        """
        Condition method.
        """
        return self.eof

    def isPaused(self, arg):
        """
        Condition method.
        """
        _, pause, _ = arg
        return pause > 0

    def doInit(self, arg):
        """
        Action method.
        """
        self.creation_time = time.time()
        self.period_time = time.time()
        self.output_limit_bytes_per_sec = get_global_output_limit_bytes_per_sec() / \
            len(streams())
        self.input_limit_bytes_per_sec = get_global_input_limit_bytes_per_sec() / \
            len(streams())
        if self.producer.session.min_rtt is not None:
            self.output_rtt_avarage = self.producer.session.min_rtt
        else:
            self.output_rtt_avarage = (RTT_MIN_LIMIT + RTT_MAX_LIMIT) / 2.0
        if _Debug:
            lg.out(self.debug_level, 'udp_stream.doInit %d with %s limits: (in=%r|out=%r)  rtt=%r' % (
                self.stream_id,
                self.producer.session.peer_id,
                self.input_limit_bytes_per_sec,
                self.output_limit_bytes_per_sec,
                self.output_rtt_avarage))

    def doPushBlocks(self, arg):
        """
        Action method.
        """
        self._push_blocks(arg)

    def doResendBlocks(self, arg):
        """
        Action method.
        """
        self._resend_blocks()

    def doResendAck(self, arg):
        """
        Action method.
        """
        self._resend_ack()

    def doSendingLoop(self, arg):
        """
        Action method.
        """
        self._sending_loop()

    def doReceivingLoop(self, arg):
        """
        Action method.
        """
        self._receiving_loop()

    def doResumeLater(self, arg):
        """
        Action method.
        """
        _, pause, remote_side_limit_receiving = arg
        if pause > 0:
            reactor.callLater(pause, self.automat, 'resume')
        if remote_side_limit_receiving > 0:
            self.output_limit_bytes_per_sec_from_remote = remote_side_limit_receiving

    def doReportSendDone(self, arg):
        """
        Action method.
        """
        if _Debug:
            lg.out(
                self.debug_level, 'udp_stream.doReportSendDone %r %r' %
                (self.consumer, self.consumer.is_done()))
        if self.consumer.is_done():
            self.consumer.status = 'finished'
        else:
            self.consumer.status = 'failed'
            self.consumer.error_message = 'sending was not finished correctly'
        self.producer.on_outbox_file_done(self.stream_id)

    def doReportSendTimeout(self, arg):
        """
        Action method.
        """
        if self.input_ack_last_time == 0:
            self.consumer.error_message = 'sending failed'
        else:
            self.consumer.error_message = 'remote side stopped responding'
        self.consumer.status = 'failed'
        self.consumer.timeout = True
        self.producer.on_timeout_sending(self.stream_id)

    def doReportReceiveDone(self, arg):
        """
        Action method.
        """
        self.consumer.status = 'finished'
        self.producer.on_inbox_file_done(self.stream_id)

    def doReportReceiveTimeout(self, arg):
        """
        Action method.
        """
        self.consumer.error_message = 'receiving timeout'
        self.consumer.status = 'failed'
        self.consumer.timeout = True
        self.producer.on_timeout_receiving(self.stream_id)

    def doReportClosed(self, arg):
        """
        Action method.
        """
        if _Debug:
            lg.out(self.debug_level, 'CLOSED %s' % self.stream_id)

    def doReportError(self, arg):
        """
        Action method.
        """
        if _Debug:
            lg.out(2, 'udp_stream.doReportError')

    def doCloseStream(self, arg):
        """
        Action method.
        """
        if _Debug:
            pir_id = self.producer.session.peer_id
            dt = time.time() - self.creation_time
            if dt == 0:
                dt = 1.0
            ratein = self.input_bytes_received / dt
            rateout = self.output_bytes_sent / dt
            extra_acks_perc = 100.0 * self.input_acks_garbage_counter / \
                float(self.output_blocks_acked + 1)
            extra_blocks_perc = 100.0 * self.output_blocks_retries / \
                float(self.output_block_id_current + 1)
            lg.out(
                self.debug_level, 'udp_stream.doCloseStream %d %s' %
                (self.stream_id, pir_id))
            lg.out(self.debug_level, '    in:%d|%d acks:%d|%d dups:%d|%d out:%d|%d|%d|%d rate:%r|%r extra:A%s|B%s' % (
                self.input_blocks_counter,
                self.input_bytes_received,
                self.output_acks_counter,
                self.output_bytes_in_acks,
                self.input_duplicated_blocks,
                self.input_duplicated_bytes,
                self.output_blocks_counter,
                self.output_bytes_acked,
                self.output_blocks_retries,
                self.input_acks_garbage_counter,
                int(ratein), int(rateout),
                misc.percent2string(extra_acks_perc),
                misc.percent2string(extra_blocks_perc)))
            lg.out(self.debug_level, '    ACK REASONS: %r' % self.output_acks_reasons)
            del pir_id
        self.input_blocks.clear()
        self.input_blocks_to_ack = []
        self.output_blocks.clear()
        self.output_blocks_ids = []

    def doUpdateLimits(self, arg):
        """
        Action method.
        """
        new_limit_receive, new_limit_send = arg
        self.input_limit_bytes_per_sec = new_limit_receive
        self.output_limit_bytes_per_sec = new_limit_send
        self.output_limit_factor = SENDING_LIMIT_FACTOR_ON_START
        if _Debug:
            lg.out(self.debug_level + 6, 'udp_stream[%d].doUpdateLimits in=%r out=%r (remote=%r)' % (
                self.stream_id,
                self.input_limit_bytes_per_sec, self.output_limit_bytes_per_sec,
                self.output_limit_bytes_per_sec_from_remote))

    def doDestroyMe(self, arg):
        """
        Action method.
        Remove all references to the state machine object to destroy it.
        """
        self.consumer.clear_stream_callback()
        self.producer.on_close_consumer(self.consumer)
        self.consumer = None
        self.producer.on_close_stream(self.stream_id)
        self.producer = None
        streams().pop(self.stream_id)
        self.destroy()
        reactor.callLater(0, balance_streams_limits)

    def on_block_received(self, inpt):
        if self.consumer and getattr(self.consumer, 'on_received_raw_data', None):
            #--- RECEIVE DATA HERE!
            block_id = inpt.read(4)
            try:
                block_id = struct.unpack('i', block_id)[0]
            except:
                lg.exc()
                if _Debug:
                    lg.out(self.debug_level, 'ERROR receiving, stream_id=%s' % self.stream_id)
                return
            #--- read block data
            data = inpt.read()
            self.input_block_last_time = time.time() - self.creation_time
            self.input_blocks_counter += 1
            if block_id != -1:
            #--- not empty block received
                self.input_bytes_received += len(data)
                self.input_block_id_last = block_id
                eof = False
                raw_size = 0
                if block_id in self.input_blocks.keys():
            #--- duplicated block received
                    self.input_duplicated_blocks += 1
                    self.input_duplicated_bytes += len(data)
                    bisect.insort(self.input_blocks_to_ack, block_id)
                else:
                    if block_id < self.input_block_id_current:
            #--- old block (already processed) received
                        self.input_old_blocks += 1
                        self.input_duplicated_bytes += len(data)
                        bisect.insort(self.input_blocks_to_ack, block_id)
                    else:
            #--- GOOD BLOCK RECEIVED
                        self.input_blocks[block_id] = data
                        bisect.insort(self.input_blocks_to_ack, block_id)
                if block_id == self.input_block_id_current + 1:
            #--- receiving data and check every next block one by one
                    newdata = cStringIO.StringIO()
                    while True:
                        next_block_id = self.input_block_id_current + 1
                        try:
                            blockdata = self.input_blocks.pop(next_block_id)
                        except KeyError:
                            break
                        newdata.write(blockdata)
                        raw_size += len(blockdata)
                        self.input_block_id_current = next_block_id
                    try:
            #--- consume data and get EOF state
                        eof = self.consumer.on_received_raw_data(newdata.getvalue())
                    except:
                        lg.exc()
                    newdata.close()
            #--- remember EOF state
                if eof and not self.eof:
                    self.eof = eof
                    if _Debug:
                        lg.out(self.debug_level, '    EOF flag set !!!!!!!! : %d' % self.stream_id)
                if _Debug:
                    lg.out(self.debug_level + 6, 'in-> BLOCK %d %r %d-%d %d %d %d' % (
                        self.stream_id,
                        self.eof,
                        block_id,
                        self.input_block_id_current,
                        self.input_bytes_received,
                        self.input_blocks_counter,
                        len(self.input_blocks_to_ack)))
            else:
                if _Debug:
                    lg.out(self.debug_level - 6, 'in-> BLOCK %d %r EMPTY %d %d' % (
                        self.stream_id, self.eof, self.input_bytes_received, self.input_blocks_counter))
            #--- raise 'block-received' event
            self.event('block-received', (block_id, data))

    def on_ack_received(self, inpt):
        if self.consumer and getattr(self.consumer, 'on_sent_raw_data', None):
#             try:
            #--- read ACK
                eof = False
                eof_flag = None
                acks = []
                pause_time = 0.0
                remote_side_limit_receiving = -1
                raw_bytes = ''
                self.input_ack_last_time = time.time() - self.creation_time
                raw_bytes = inpt.read(1)
                if len(raw_bytes) > 0:
            #--- read EOF state from ACK
                    eof_flag = struct.unpack('?', raw_bytes)[0]
#                 else:
#                     eof_flag = True
#                 if not eof_flag:
                if True:
                    while True:
                        raw_bytes = inpt.read(4)
                        if len(raw_bytes) == 0:
                            break
            #--- read block id from ACK
                        block_id = struct.unpack('i', raw_bytes)[0]
                        if block_id >= 0:
                            acks.append(block_id)
                        elif block_id == -1:
            #--- read PAUSE TIME from ACK
                            raw_bytes = inpt.read(4)
                            if not raw_bytes:
                                lg.warn('wrong ack: not found pause time')
                                break
                            pause_time = struct.unpack('f', raw_bytes)[0]
            #--- read remote bandwith limit from ACK
                            raw_bytes = inpt.read(4)
                            if not raw_bytes:
                                lg.warn('wrong ack: not found remote bandwith limit')
                                break
                            remote_side_limit_receiving = struct.unpack('f', raw_bytes)[0]
                        else:
                            lg.warn('incorrect block_id received: %r' % block_id)
                if len(acks) > 0:
            #--- some blocks was received fine
                    self.input_acks_counter += 1
                if pause_time == 0.0 and eof_flag:
            #--- EOF state found in the ACK
                    if _Debug:
                        sum_not_acked_blocks = sum(map(lambda block: len(block[0]),
                                                       self.output_blocks.values()))
#                     self.output_bytes_acked += sum_not_acked_blocks
#                     eof = self.consumer.on_sent_raw_data(sum_not_acked_blocks)
                        try:
                            sz = self.consumer.size
                        except:
                            sz = -1
                        lg.out(self.debug_level - 6, '    EOF state found in ACK %d acked:%d not acked:%d total:%d' % (
                            self.stream_id, self.output_bytes_acked, sum_not_acked_blocks, sz))
                for block_id in acks:
            #--- mark this block as acked
                    if block_id >= self.output_acked_block_id_current:
                        if block_id not in self.output_acked_blocks_ids:
                            # bisect.insort(self.output_acked_blocks_ids, block_id)
                            self.output_acked_blocks_ids.add(block_id)
                    if block_id not in self.output_blocks_ids or block_id not in self.output_blocks:
            #--- garbage, block was already acked
                        self.input_acks_garbage_counter += 1
                        if _Debug:
                            lg.out(self.debug_level + 6, '    GARBAGE ACK, block %d not found, stream_id=%d' % (
                                block_id, self.stream_id))
                        continue
            #--- mark block as acked
                    self.output_blocks_ids.remove(block_id)
                    outblock = self.output_blocks.pop(block_id)
                    block_size = len(outblock[0])
                    self.output_bytes_acked += block_size
                    self.output_buffer_size -= block_size
                    self.output_blocks_success_counter += 1.0
                    self.output_quality_counter += 1.0
                    relative_time = time.time() - self.creation_time
                    last_ack_rtt = relative_time - outblock[1]
                    self.output_rtt_avarage += last_ack_rtt
                    self.output_rtt_counter += 1.0
            #--- drop avarage RTT
                    if self.output_rtt_counter > MAX_RTT_COUNTER:
                        rtt_avarage_dropped = self.output_rtt_avarage / self.output_rtt_counter
                        self.output_rtt_counter = round(MAX_RTT_COUNTER / 2.0, 0)
                        self.output_rtt_avarage = rtt_avarage_dropped * self.output_rtt_counter
            #--- process delivered data
                    eof = self.consumer.on_sent_raw_data(block_size)
                    if eof:
                        if _Debug:
                            lg.out(self.debug_level - 6, '    EOF state from consumer : %d' % self.stream_id)
                for block_id in self.output_blocks_ids:
            #--- mark blocks which was not acked in this ACK
                    self.output_blocks[block_id][2] += 1
                while True:
                    next_block_id = self.output_acked_block_id_current + 1
                    try:
                        self.output_acked_blocks_ids.remove(next_block_id)
                    except KeyError:
                        break
                    self.output_acked_block_id_current = next_block_id
                    self.output_blocks_acked += 1
                eof = eof or eof_flag
                if not self.eof and eof:
            #--- remember EOF state
                    self.eof = eof
                    if _Debug:
                        lg.out(self.debug_level - 6, '    EOF RICHED !!!!!!!! : %d' % self.stream_id)
                if _Debug:
                    try:
                        sz = self.consumer.size
                    except:
                        sz = -1
                    if pause_time > 0:
                        lg.out(self.debug_level + 6, 'in-> ACK %d PAUSE:%r %s %d %s %d %d %r' % (
                            self.stream_id, pause_time, acks, len(self.output_blocks),
                            eof, sz, self.output_bytes_acked, acks))
                        lg.out(self.debug_level + 6, '    %r' % self.output_acked_blocks_ids)
                    else:
                        lg.out(self.debug_level + 6, 'in-> ACK %d %d %d %s %d %d %r' % (
                            self.stream_id, self.output_acked_block_id_current,
                            len(self.output_blocks), eof, self.output_bytes_acked, sz, acks))
                self.event('ack-received', (acks, pause_time, remote_side_limit_receiving))
#             except:
#                 lg.exc()

    def on_consume(self, data):
        if self.consumer:
            if self.output_buffer_size + len(data) > OUTPUT_BUFFER_SIZE:
                raise BufferOverflow(self.output_buffer_size)
            if self.output_block_id_current - self.output_acked_block_id_current > BLOCKS_PER_ACK * 10:
                raise BufferOverflow(self.output_buffer_size)
            self.event('consume', data)

    def on_close(self):
        if _Debug:
            lg.out(self.debug_level, 'udp_stream.UDPStream[%d].on_close, send "close" event to the stream' % self.stream_id)
        if self.consumer:
            reactor.callLater(0, self.automat, 'close')

    def _push_blocks(self, data):
        outp = cStringIO.StringIO(data)
        while True:
            piece = outp.read(BLOCK_SIZE)
            if not piece:
                break
            self.output_block_id_current += 1
            #--- prepare block to be send
            bisect.insort(self.output_blocks_ids, self.output_block_id_current)
            # data, time_sent, acks_missed
            self.output_blocks[self.output_block_id_current] = [piece, -1, 0]
            self.output_buffer_size += len(piece)
        outp.close()
        if _Debug:
            lg.out(self.debug_level + 6, 'PUSH %d [%s]' % (
                self.output_block_id_current, ','.join(map(str, self.output_blocks_ids)), ))

    def _sending_loop(self):
        total_rate_out = 0.0
#         current_rate_out = 0.0
        relative_time = time.time() - self.creation_time
        if relative_time > 0:
            total_rate_out = self.output_bytes_sent / float(relative_time)
#         verification_period = time.time() - self.period_time
#         if verification_period > 0:
#             current_rate_out = self.output_bytes_sent_period / float(verification_period)
#         if verification_period > 1.0:   # POOLING_INTERVAL * 20:
#             self.output_bytes_per_sec_last = current_rate_out
#             self.output_bytes_sent_period = 0
#             self.period_time = time.time()
#         if self.output_quality_counter > MAX_RTT_COUNTER * 100:
#             new_counter = round(100 * MAX_RTT_COUNTER / 2.0, 0)
#             self.output_blocks_success_counter = round(
#                 new_counter * (self.output_blocks_success_counter / self.output_quality_counter), 0)
#             self.output_blocks_timed_out_counter = round(
#                 new_counter * (self.output_blocks_timed_out_counter / self.output_quality_counter), 0)
#             # self.output_blocks_lagged_counter = round(
#             #     new_counter * (self.output_blocks_lagged_counter / self.output_quality_counter), 0)
#             self.output_quality_counter = new_counter
        if lg.is_debug(self.debug_level):
            if relative_time - self.last_progress_report > POOLING_INTERVAL * 50.0:
                if _Debug:
                    lg.out(self.debug_level, 'udp_stream[%d]|%d/%r%%|garb.:%d/%d|err.:%r%%/%r%%|%rbps|pkt:%d/%d|RTT:%r|lag:%d|last:%r|buf:%d' % (
                        self.stream_id,
                        #--- current block acked/percent sent
                        self.output_acked_block_id_current,
                        round(100.0 * (float(self.output_bytes_acked) / self.consumer.size), 2),
                        #--- garbage blocks out/garbacge acks in
                        self.output_blocks_retries, self.input_acks_garbage_counter,
                        #--- errors timeouts/lagged/success %/error %
                        # self.output_blocks_timed_out_counter,
                        # self.output_blocks_lagged_counter,
                        # self.output_blocks_lagged_counter,
                        round(100.0 * (self.output_blocks_timed_out_counter / (self.output_quality_counter + 1)), 2),
                        # round(100.0 * (self.output_blocks_lagged_counter / (self.output_quality_counter + 1)), 2),
                        round(100.0 * (self.output_blocks_success_counter / (self.output_quality_counter + 1)), 2),
                        #--- sending speed current/total
                        # int(current_rate_out),
                        int(total_rate_out),
                        # self.output_limit_factor,
                        # #--- bytes out/in
                        # self.output_bytes_sent, self.output_bytes_acked,
                        #--- blocks out/acks in
                        self.output_blocks_counter, self.input_acks_counter,
                        #--- current avarage RTT
                        round(self.output_rtt_avarage / self.output_rtt_counter, 4),
                        #--- current lag
                        (self.output_block_id_current - self.output_acked_block_id_current),
                        #--- last ACK received
                        round(relative_time - self.input_ack_last_time, 4),
                        #--- packets in buffer/window size
                        len(self.output_blocks),
                    ))
                self.last_progress_report = relative_time

    def _receiving_loop(self):
        if lg.is_debug(self.debug_level):
            relative_time = time.time() - self.creation_time
            if relative_time - self.last_progress_report > POOLING_INTERVAL * 50.0:
                if _Debug:
                    lg.out(self.debug_level, 'udp_stream[%d] | %d/%r%% | garb.:%d/%d | %d bps | b.:%d/%d | pkt.:%d/%d | last: %r | buf: %d' % (
                        self.stream_id,
                        #--- percent received
                        self.input_block_id_current,
                        round(100.0 * (float(self.consumer.bytes_received) / self.consumer.size), 2),
                        #--- garbage blocks duplicated/old
                        self.input_duplicated_blocks, self.input_old_blocks,
                        #--- garbage blocks ratio
                        # round(100.0 * (float(self.input_blocks_counter + 1) / float(self.input_block_id_current + 1)), 2),
                        #--- receiving speed
                        int(self.input_bytes_per_sec_current),
                        #--- bytes in/consumed
                        self.input_bytes_received, self.consumer.bytes_received,
                        #--- blocks in/acks out
                        self.input_blocks_counter, self.output_acks_counter,
                        #--- last BLOCK received
                        round(relative_time - self.input_block_last_time, 4),
                        #--- input buffer
                        len(self.input_blocks),
                    ))
                self.last_progress_report = relative_time

    def _resend_blocks(self):
        if len(self.output_blocks) == 0:
            #--- nothing to send right now
            return
        relative_time = time.time() - self.creation_time
        # period_time = time.time() - self.period_time
        current_limit = self._get_output_limit_bytes_per_sec()
        # band_limit = False
        # if self.output_bytes_per_sec_last > 0 or period_time > 0:
        if current_limit > 0 and relative_time > 0.5:  # and period_time > 0:
            current_rate = self.output_bytes_sent / relative_time
            # period_rate = self.output_bytes_sent_period / period_time
            if current_rate > current_limit:  # and current_rate > period_rate:
            # if current_rate > self.output_bytes_per_sec_last:
            # if self.output_bytes_per_sec_last > current_limit or period_rate > current_limit:
            #--- skip sending : bandwidth limit reached
                # band_limit = True
                if _Debug:
                    lg.out(self.debug_level + 6, 'SKIP RESENDING %d, bandwidth limit : %r>%r, factor: %r, remote: %r' % (
                        self.stream_id,
                        int(current_rate),
                        int(self.output_limit_bytes_per_sec * self.output_limit_factor),
                        self.output_limit_factor,
                        self.output_limit_bytes_per_sec_from_remote))
                return
        if self.input_acks_counter > 0:
            #--- got some acks already
            if self.output_blocks_counter / float(self.input_acks_counter) > BLOCKS_PER_ACK * 2:
            #--- too many blocks sent but few acks
                if self.state == 'SENDING' or self.state == 'PAUSE':
            #--- check sending timeout
                    if relative_time - self.input_ack_last_time > RTT_MAX_LIMIT * 3:
            #--- no responding activity at all
                        if _Debug:
                            lg.out(
                                self.debug_level,
                                'TIMEOUT SENDING rtt=%r, last ack at %r, last block was %r, reltime is %r' %
                                (self.output_rtt_avarage /
                                 self.output_rtt_counter,
                                 self.input_ack_last_time,
                                 self.output_block_last_time,
                                 relative_time))
                        reactor.callLater(0, self.automat, 'timeout')
                        return
            #--- skip sending : too few acks
                if _Debug:
                    lg.out(self.debug_level + 6, 'SKIP SENDING %d, too few acks:%d blocks:%d' % (
                        self.stream_id, self.input_acks_counter, self.output_blocks_counter))
                # seems like sending too fast
                return
        if self.output_block_last_time - self.input_ack_last_time > RTT_MAX_LIMIT * 2.0:
            #--- last ack was timed out
            self.input_acks_timeouts_counter += 1
            if self.input_acks_timeouts_counter >= MAX_ACK_TIMEOUTS:
            #--- timeout sending : too many timed out acks
                if _Debug:
                    lg.out(self.debug_level, 'SENDING BROKEN %d rtt=%r, last ack at %r, last block was %r' % (
                        self.stream_id,
                        self.output_rtt_avarage /
                        self.output_rtt_counter,
                        self.input_ack_last_time,
                        self.output_block_last_time))
                reactor.callLater(0, self.automat, 'timeout')
            else:
                if self.output_blocks_ids:
            #--- resend one "oldest" block
                    blocks_not_acked = sorted(self.output_blocks_ids,
                                              # key=lambda bid: self.output_blocks[bid][2],
                                              # reverse=True,
                                              )
                    latest_block_id = blocks_not_acked[0]
                    self.output_blocks_retries += 1
                    if _Debug:
                        lg.out(self.debug_level - 6, 'RESEND ONE %d %d' % (
                            self.stream_id, latest_block_id))
                    self._send_blocks([latest_block_id, ])
                else:
            #--- no activity at all
                    if _Debug:
                        lg.out(self.debug_level, 'SKIP SENDING %d, no blocks to send now' % self.stream_id)
            return
            #--- normal sending, check all pending blocks
        rtt_current = self._rtt_current()  # self.output_rtt_avarage / self.output_rtt_counter
        resend_time_limit = min(BLOCKS_PER_ACK * rtt_current * 2, RTT_MAX_LIMIT)
        # resend_time_limit = BLOCKS_PER_ACK * ( ( RTT_MIN_LIMIT + RTT_MAX_LIMIT ) / 2.0 ) * 2.0
        # resend_time_limit = ( RTT_MIN_LIMIT + RTT_MAX_LIMIT ) / 2.0
        # resend_time_limit = RTT_MAX_LIMIT
        # current_lag = self.output_block_id_current - self.output_acked_block_id_current
        blocks_to_send_now = []
        for block_id in self.output_blocks_ids:
            if len(blocks_to_send_now) > BLOCKS_PER_ACK:
            #--- do not send too much blocks at once
                break
            # if band_limit and len(blocks_to_send_now) > 0:
            #--- send only one block if sending over band limit
            #     break
            #--- decide to send the block now
            time_sent, _ = self.output_blocks[block_id][1:3]
            if time_sent != -1:
                continue
            #--- send this block first time
            blocks_to_send_now.append(block_id)
        if not blocks_to_send_now:
            #--- all current blocks was sent here, check for timed out blocks
            blocks_not_acked = sorted(self.output_blocks_ids,
                                      # key=lambda bid: self.output_blocks[bid][2],
                                      # reverse=True,
                                      )
            for block_id in blocks_not_acked:
                if len(blocks_to_send_now) > BLOCKS_PER_ACK:
            #--- do not send too much blocks at once
                    break
                time_sent, _ = self.output_blocks[block_id][1:3]
                timed_out = time_sent >= 0 and (
                    relative_time - time_sent > resend_time_limit)
                if timed_out:
            #--- this block was timed out, resending
                    blocks_to_send_now.insert(0, block_id)
                    self.output_blocks_retries += 1
#                     self.output_blocks_errors_counter += 1.0
                    self.output_blocks_timed_out_counter += 1
                    self.output_quality_counter += 1.0
#                     continue
    #             if current_lag > BLOCKS_PER_ACK * 100:
    #             #--- lag, this block was not delivered, resending
    #                 if block_id - self.output_acked_block_id_current < BLOCKS_PER_ACK:
    #                     blocks_to_send_now.insert(0, block_id)
    #                     self.output_blocks_retries += 1
    #                     self.output_blocks_lagged += 1
    #                     self.output_blocks_errors_counter += 1.0
    #                     self.output_quality_counter += 1.0
        if blocks_to_send_now:
            #--- sending blocks now
            self._send_blocks(blocks_to_send_now)
        del blocks_to_send_now

    def _send_blocks(self, blocks_to_send):
        current_limit = self._get_output_limit_bytes_per_sec()
        relative_time = time.time() - self.creation_time
        # period_time = time.time() - self.period_time
        new_blocks_counter = 0
        limit_sending = False
        for block_id in blocks_to_send:
            piece = self.output_blocks[block_id][0]
            data_size = len(piece)
            if len(blocks_to_send) > 1 and current_limit > 0 and relative_time > 0:  # and period_time > 0:
            # if self.output_bytes_per_sec_last > 0 or period_time > 0:
            #--- limit sending, current rate is too big
                current_rate = (self.output_bytes_sent + data_size) / relative_time
                # period_rate = (self.output_bytes_sent_period + data_size) / period_time
                if current_rate > current_limit:  # and current_rate > period_time:
                # if self.output_bytes_per_sec_last > current_limit or period_rate > current_limit:
                    if new_blocks_counter > 0:
                        limit_sending = True
                        break
                    if self.output_ack_last_time < RTT_MAX_LIMIT:
                        limit_sending = True
                        break
            output = ''.join((struct.pack('i', block_id), piece))
            #--- SEND DATA HERE!
            if not self.producer.do_send_data(self.stream_id, self.consumer, output):
                # self.output_blocks_lagged_counter += 1
#                 self.output_quality_counter += 1.0
                limit_sending = True
                # import pdb
                # pdb.set_trace()
                break
            #--- mark block as sent
            self.output_blocks[block_id][1] = relative_time
            #--- erase acks received for this block
            self.output_blocks[block_id][2] = 0
            self.output_bytes_sent += data_size
            self.output_bytes_sent_period += data_size
            self.output_blocks_counter += 1
            new_blocks_counter += 1
            self.output_block_last_time = relative_time
            if _Debug:
                lg.out(self.debug_level + 6, '<-out BLOCK %d %r %r %d/%d' % (
                    self.stream_id,
                    self.eof,
                    block_id,
                    self.output_bytes_sent,
                    self.output_bytes_acked))
        if relative_time > 0:
            #--- calculate current sending speed
            self.output_bytes_per_sec_current = self.output_bytes_sent / relative_time
        if limit_sending:
            if _Debug:
                lg.out(self.debug_level + 6, 'SKIP SENDING %d, bandwidth limit : %r>%r, factor: %r, remote: %r' % (
                    self.stream_id,
                    int(current_rate),
                    int(self.output_limit_bytes_per_sec * self.output_limit_factor),
                    self.output_limit_factor,
                    self.output_limit_bytes_per_sec_from_remote))

    def _resend_ack(self):
        if self.output_acks_counter == 0:
            #--- do send first ACK
            self._send_ack(self.input_blocks_to_ack)
            return
        if self._block_period_avarage() == 0:
            #--- SKIP: block frequency is unknown
            # that means no input block was received yet
            # , do send first ACK
            # self._send_ack(self.input_blocks_to_ack)
            return
        relative_time = time.time() - self.creation_time
        pause_time = 0.0
        if relative_time > 0:
            #--- calculate current receiving speed
            self.input_bytes_per_sec_current = self.input_bytes_received / relative_time
        if self.input_limit_bytes_per_sec > 0 and relative_time > 0:
            max_receive_available = self.input_limit_bytes_per_sec * relative_time
            if self.input_bytes_received > max_receive_available:
            #--- limit receiving, calculate pause time
                pause_time = (self.input_bytes_received - max_receive_available) / self.input_limit_bytes_per_sec
                if pause_time < 0:
                    lg.warn('pause is %r, stream_id=%d' % (pause_time, self.stream_id))
                    pause_time = 0.0
        if relative_time - self.input_block_last_time > RECEIVING_TIMEOUT:
            #--- last block came long time ago, timeout receiving
            if _Debug:
                lg.out(self.debug_level - 6, 'TIMEOUT RECEIVING %d rtt=%r, last block in %r, reltime: %r, eof: %r, blocks to ack: %d' % (
                    self.stream_id, self._rtt_current(), self.input_block_last_time,
                    relative_time, self.eof, len(self.input_blocks_to_ack),))
            reactor.callLater(0, self.automat, 'timeout')
            return
        if len(self.input_blocks_to_ack) > BLOCKS_PER_ACK:
            #--- received enough blocks to make a group, send ACK
            self._send_ack(self.input_blocks_to_ack, pause_time, why=1)
            return
#         if (self.input_block_id_last % BLOCKS_PER_ACK) == 1:
#             #--- first block in group, send ACK
#             # need to send ACK for every N blocks recevied
#             # so when received a block with block_id % N == 1
#             # means this is a next group of blocks started
#             # so need to send an ack for previous group
#             self._send_ack(self.input_blocks_to_ack, pause_time, why=2)
#             return
        if self.eof:
            #--- at EOF state, send ACK
            self._send_ack(self.input_blocks_to_ack, pause_time, why=3)
            return
        if self._last_ack_timed_out():
            #--- last ack has been long time ago, send ACK
            self._send_ack(self.input_blocks_to_ack, pause_time, why=4)
            return
#         if self.input_block_id_current > 0 and self.input_block_id_last < self.input_block_id_current:
#             #--- last block already processed, send garbage ACK
#             # so here need to send "garbage ACK" to notify that
#             # this old block was already porcessed
#             self._send_ack(self.input_blocks_to_ack, pause_time, why=5)
#             return
#         if _Debug:
#             lg.out(self.debug_level - 6, 'SKIP sending any ACKS %d' % (self.stream_id))

    def _send_ack(self, acks, pause_time=0.0, why=0):
        if len(acks) == 0 and pause_time == 0.0 and not self.eof:
        #--- SKIP: no pending ACKS, no PAUSE, no EOF
            return
        #--- prepare EOF state in ACK
        ack_data = struct.pack('?', self.eof)
        #--- prepare ACKS
        ack_data += ''.join(map(lambda bid: struct.pack('i', bid), acks))
        if pause_time > 0:
        #--- add extra "PAUSE REQUIRED" ACK
            ack_data += struct.pack('i', -1)
            ack_data += struct.pack('f', pause_time)
            ack_data += struct.pack('f', self.input_limit_bytes_per_sec)
        ack_len = len(ack_data)
        self.output_bytes_in_acks += ack_len
        self.output_acks_counter += 1
        self.input_blocks_to_ack = []
        self.output_ack_last_time = time.time()
        if _Debug:
            if pause_time <= 0.0:
                lg.out(self.debug_level + 6, '<-out ACK %d %r %r %d/%d' % (
                    self.stream_id, self.eof, acks,
                    self.input_bytes_received,
                    self.consumer.bytes_received))
            else:
                lg.out(self.debug_level - 6, '<-out ACK %d %r PAUSE:%r LIMIT:%r %r' % (
                    self.stream_id, self.eof, pause_time, self.input_limit_bytes_per_sec, acks))
        self.producer.do_send_ack(self.stream_id, self.consumer, ack_data)
        if why not in self.output_acks_reasons:
            self.output_acks_reasons[why] = 1
        else:
            self.output_acks_reasons[why] += 1
        return ack_len > 0

    def _rtt_current(self):
        rtt_current = self.output_rtt_avarage / self.output_rtt_counter
        return rtt_current

    def _block_period_avarage(self):
        if self.input_blocks_counter == 0:
            return 0
        return (time.time() - self.creation_time) / float(self.input_blocks_counter)

    def _last_ack_timed_out(self):
        return time.time() - self.output_ack_last_time > RTT_MAX_LIMIT

    def _get_output_limit_bytes_per_sec(self):
        global _CurrentSendingAvarageRate
        own_limit = self.output_limit_bytes_per_sec * self.output_limit_factor
        if _CurrentSendingAvarageRate > 0:
            own_limit = min(own_limit, _CurrentSendingAvarageRate * 3.0)
        if self.output_limit_bytes_per_sec_from_remote < 0:
            return own_limit
        return min(own_limit, self.output_limit_bytes_per_sec_from_remote)

    def get_current_output_bytes_per_sec(self):
        relative_time = time.time() - self.creation_time
        if relative_time < 0.5:
            return 0.0
        return self.output_bytes_sent / relative_time
