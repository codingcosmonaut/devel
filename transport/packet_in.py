#!/usr/bin/env python
# packet_in.py
#
# Copyright (C) 2008-2016 Veselin Penev, http://bitdust.io
#
# This file (packet_in.py) is part of BitDust Software.
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
.. module:: packet_in.

.. role:: red

BitDust packet_in() Automat

.. raw:: html

    <a href="packet_in.png" target="_blank">
    <img src="packet_in.png" style="max-width:100%;">
    </a>

EVENTS:
    * :red:`cancel`
    * :red:`failed`
    * :red:`register-item`
    * :red:`remote-id-cached`
    * :red:`unregister-item`
    * :red:`unserialize-failed`
    * :red:`valid-inbox-packet`
"""

#------------------------------------------------------------------------------

_Debug = True
_DebugLevel = 12

#------------------------------------------------------------------------------

import os
import time

from twisted.internet import reactor

from logs import lg

from lib import misc

from main import settings

from automats import automat

from system import bpio
from system import tmpfile

from userid import my_id

from contacts import contactsdb
from contacts import identitycache

from services import driver

import gateway
import stats
import callback
import packet_out

#------------------------------------------------------------------------------

_InboxItems = {}
_PacketsCounter = 0
_History = []

#------------------------------------------------------------------------------


def get_packets_counter():
    global _PacketsCounter
    return _PacketsCounter


def increment_packets_counter():
    global _PacketsCounter
    _PacketsCounter += 1

#------------------------------------------------------------------------------


def items():
    """
    """
    global _InboxItems
    return _InboxItems


def create(transfer_id):
    p = PacketIn(transfer_id)
    items()[transfer_id] = p
    # lg.out(10, 'packet_in.create  %s,  %d working items now' % (
    #     transfer_id, len(items())))
    return p


def get(transfer_id):
    return items().get(transfer_id, None)


def history():
    global _History
    return _History

#------------------------------------------------------------------------------


def process(newpacket, info):
    if not driver.is_started('service_p2p_hookups'):
        if _Debug:
            lg.out(_DebugLevel, 'packet_in.process SKIP incoming packet, service_p2p_hookups is not started')
        return
    handled = False
    if _Debug:
        lg.out(_DebugLevel, 'packet_in.process %s from %s://%s : %s' % (
            str(newpacket), info.proto, info.host, info.status))
    from p2p import commands
    from p2p import p2p_service
    if newpacket.Command == commands.Identity() and newpacket.RemoteID == my_id.getLocalID():
        # contact sending us current identity we might not have
        # so we handle it before check that packet is valid
        # because we might not have his identity on hands and so can not verify the packet
        # so we check that his Identity is valid and save it into cache
        # than we check the packet to be valid too.
        if not p2p_service.Identity(newpacket):
            return
    # check that signed by a contact of ours
    if not newpacket.Valid():
        lg.warn('new packet from %s://%s is NOT VALID: %r' % (
            info.proto, info.host, newpacket))
        return
    for p in packet_out.search_by_response_packet(newpacket, info.proto, info.host):
        p.automat('inbox-packet', (newpacket, info))
        handled = True
    handled = callback.run_inbox_callbacks(newpacket, info, info.status, info.error_message) or handled
    if not handled and newpacket.Command not in [commands.Ack(), commands.Fail()]:
        if _Debug:
            lg.out(_DebugLevel - 8, '    incoming %s from [%s://%s]' % (
                newpacket, info.proto, info.host))
            lg.out(_DebugLevel - 8, '        NOT HANDLED !!!')
    if _Debug:
        history().append({
            'time': newpacket.Date,
            'command': newpacket.Command,
            'packet_id': newpacket.PacketID,
            'creator_id': newpacket.CreatorID,
            'owner_id': newpacket.OwnerID,
            'remote_id': newpacket.RemoteID,
            'payload': len(newpacket.Payload),
            'address': '%s://%s' % (info.proto, info.host),
        })
        if len(history()) > 100:
            history().pop(0)

#------------------------------------------------------------------------------


class PacketIn(automat.Automat):
    """
    This class implements all the functionality of the ``packet_in()`` state
    machine.
    """

    def __init__(self, transfer_id):
        self.transfer_id = transfer_id
        self.time = None
        self.timeout = None
        self.proto = None
        self.host = None
        self.sender_idurl = None
        self.filename = None
        self.size = None
        self.bytes_received = None
        self.status = None
        self.error_message = None
        self.label = 'in_%d_%s' % (get_packets_counter(), self.transfer_id)
        automat.Automat.__init__(self, self.label, 'AT_STARTUP', _DebugLevel, _Debug)
        increment_packets_counter()

    def is_timed_out(self):
        return False
#         if self.time is None or self.timeout is None:
#             return False
#         return time.time() - self.time > self.timeout

    def init(self):
        """
        Method to initialize additional variables and flags at creation of the
        state machine.
        """
        self.log_events = False

    def A(self, event, arg):
        #---AT_STARTUP---
        if self.state == 'AT_STARTUP':
            if event == 'register-item':
                self.state = 'RECEIVING'
                self.doInit(arg)
        #---RECEIVING---
        elif self.state == 'RECEIVING':
            if event == 'cancel':
                self.doCancelItem(arg)
            elif event == 'unregister-item' and not self.isTransferFinished(arg):
                self.state = 'FAILED'
                self.doReportFailed(arg)
                self.doEraseInputFile(arg)
                self.doDestroyMe(arg)
            elif event == 'unregister-item' and self.isTransferFinished(arg) and not self.isRemoteIdentityCached(arg):
                self.state = 'CACHING'
                self.doCacheRemoteIdentity(arg)
            elif event == 'unregister-item' and self.isTransferFinished(arg) and self.isRemoteIdentityCached(arg):
                self.state = 'INBOX?'
                self.doReadAndUnserialize(arg)
        #---INBOX?---
        elif self.state == 'INBOX?':
            if event == 'valid-inbox-packet':
                self.state = 'DONE'
                self.doReportReceived(arg)
                self.doEraseInputFile(arg)
                self.doDestroyMe(arg)
            elif event == 'unserialize-failed':
                self.state = 'FAILED'
                self.doReportFailed(arg)
                self.doEraseInputFile(arg)
                self.doDestroyMe(arg)
        #---FAILED---
        elif self.state == 'FAILED':
            pass
        #---DONE---
        elif self.state == 'DONE':
            pass
        #---CACHING---
        elif self.state == 'CACHING':
            if event == 'failed':
                self.state = 'FAILED'
                self.doReportCacheFailed(arg)
                self.doEraseInputFile(arg)
                self.doDestroyMe(arg)
            elif event == 'remote-id-cached':
                self.state = 'INBOX?'
                self.doReadAndUnserialize(arg)
        return None

    def isTransferFinished(self, arg):
        """
        Condition method.
        """
        status, bytes_received, _ = arg
        if status != 'finished':
            return False
        if self.size and self.size > 0 and self.size != bytes_received:
            return False
        return True

    def isRemoteIdentityCached(self, arg):
        """
        Condition method.
        """
        if not self.sender_idurl:
            return True
        return self.sender_idurl and identitycache.HasKey(self.sender_idurl)

    def doInit(self, arg):
        """
        Action method.
        """
        self.proto, self.host, self.sender_idurl, self.filename, self.size = arg
        self.time = time.time()
        # 300  # max(10 * int(self.size/float(settings.SendingSpeedLimit())), 10)
        if self.size < 1024 * 10:
            self.timeout = 10
        elif self.size > 1024 * 1024:
            self.timeout = int(self.size / float(settings.SendingSpeedLimit()))
        else:
            self.timeout = 300
        if not self.sender_idurl:
            lg.warn('sender_idurl is None: %s' % str(arg))

    def doEraseInputFile(self, arg):
        """
        Action method.
        """
        reactor.callLater(1, tmpfile.throw_out, self.filename, 'received')

    def doCancelItem(self, arg):
        """
        Action method.
        """
        t = gateway.transports().get(self.proto, None)
        if t:
            t.call('cancel_file_receiving', self.transfer_id)

    def doCacheRemoteIdentity(self, arg):
        """
        Action method.
        """
        d = identitycache.immediatelyCaching(self.sender_idurl)
        d.addCallback(self._remote_identity_cached, arg)
        d.addErrback(lambda err: self.automat('failed', arg))

    def doReadAndUnserialize(self, arg):
        """
        Action method.
        """
        self.status, self.bytes_received, self.error_message = arg
        # DO UNSERIALIZE HERE , no exceptions
        newpacket = gateway.inbox(self)
        if newpacket is None:
            if _Debug:
                lg.out(_DebugLevel, '<<< IN <<< !!!NONE!!! [%s] %s from %s %s' % (
                    self.proto.upper().ljust(5), self.status.ljust(8),
                    self.host, os.path.basename(self.filename),))
            # net_misc.ConnectionFailed(None, proto, 'receiveStatusReport %s' % host)
            try:
                fd, _ = tmpfile.make('error', '.inbox')
                data = bpio.ReadBinaryFile(self.filename)
                os.write(fd, 'from %s:%s %s\n' % (self.proto, self.host, self.status))
                os.write(fd, str(data))
                os.close(fd)
            except:
                lg.exc()
            try:
                os.remove(self.filename)
            except:
                lg.exc()
            self.automat('unserialize-failed', None)
            return
        self.label += '_%s[%s]' % (newpacket.Command, newpacket.PacketID)
        self.automat('valid-inbox-packet', newpacket)

    def doReportReceived(self, arg):
        """
        Action method.
        """
        newpacket = arg
        stats.count_inbox(self.sender_idurl, self.proto, self.status, self.bytes_received)
        process(newpacket, self)

    def doReportFailed(self, arg):
        """
        Action method.
        """
        try:
            status, bytes_received, _ = arg
        except:
            status = 'failed'
            bytes_received = 0
        stats.count_inbox(self.sender_idurl, self.proto, status, bytes_received)

    def doReportCacheFailed(self, arg):
        """
        Action method.
        """
        if arg:
            status, bytes_received, _ = arg
            stats.count_inbox(self.sender_idurl, self.proto, status, bytes_received)
        lg.out(18, 'packet_in.doReportCacheFailed WARNING : %s' % self.sender_idurl)

    def doDestroyMe(self, arg):
        """
        Remove all references to the state machine object to destroy it.
        """
        items().pop(self.transfer_id)
        self.destroy()

    def _remote_identity_cached(self, xmlsrc, arg):
        sender_identity = contactsdb.get_contact_identity(self.sender_idurl)
        if sender_identity is None:
            self.automat('failed')
        else:
            self.automat('remote-id-cached', arg)
