

"""
.. module:: udp_session

BitPie.NET udp_session() Automat


EVENTS:
    * :red:`datagram-received`
    * :red:`init`
    * :red:`shutdown`
    * :red:`timer-10sec`
    * :red:`timer-1min`
    * :red:`timer-1sec`
    * :red:`timer-30sec`
        
"""

import time

from twisted.internet import reactor

from logs import lg

from lib import misc
from lib import automat
from lib import udp

import udp_file_queue

#------------------------------------------------------------------------------ 

MIN_PROCESS_SESSIONS_DELAY = 0.001
MAX_PROCESS_SESSIONS_DELAY = 1.0
  
#------------------------------------------------------------------------------ 

_SessionsDict = {}
_KnownPeersDict = {}
_KnownUserIDsDict = {}
_PendingOutboxFiles = []
_ProcessSessionsTask = None
_ProcessSessionsDelay = MIN_PROCESS_SESSIONS_DELAY

#------------------------------------------------------------------------------ 

def sessions():
    """
    """
    global _SessionsDict
    return _SessionsDict


def create(node, peer_address, peer_id=None):
    """
    """
    lg.out(10, 'udp_session.create  peer_address=%s' % str(peer_address))
    s = UDPSession(node, peer_address, peer_id)
    sessions()[s.id] = s
    return s


def get(peer_address):
    """
    """
    # lg.out(18, 'udp_session.get %s %s' % (str(peer_address), 
    #     str(map(lambda s:s.peer_address, sessions().values()))))
    for id, s in sessions().items():
        if s.peer_address == peer_address:
            return s 
    return None


def get_by_peer_id(peer_id):
    """
    """
    for id, s in sessions().items():
        if s.peer_id == peer_id:
            return s 
    return None


def close(peer_address):
    """
    """
    s = get(peer_address)
    if s is None:
        return False
    s.automat('shutdown')
    return True


def add_pending_outbox_file(filename, host, description='', result_defer=None, single=False):
    """
    """
    global _PendingOutboxFiles
    _PendingOutboxFiles.append((filename, host, description, result_defer, single, time.time()))


def process_sessions():
    global _ProcessSessionsTask
    global _ProcessSessionsDelay
    has_activity = False
    for s in sessions().values():
        if not s.file_queue:
            continue
        has_outbox = s.file_queue.process_outbox_queue()
        has_sends = s.file_queue.process_outbox_files()    
        if has_sends or has_outbox:
            has_activity = True
    if has_activity:
        _ProcessSessionsTask = reactor.callLater(0, process_sessions)        
    else:
        _ProcessSessionsDelay = misc.LoopAttenuation(
            _ProcessSessionsDelay, has_activity, 
            MIN_PROCESS_SESSIONS_DELAY, MAX_PROCESS_SESSIONS_DELAY,)
        # attenuation
        _ProcessSessionsTask = reactor.callLater(_ProcessSessionsDelay, 
                                                 process_sessions)        

def stop_process_sessions(self):
    global _ProcessSessionsTask
    if _ProcessSessionsTask:
        if _ProcessSessionsTask.active():
            _ProcessSessionsTask.cancel()
            _ProcessSessionsTask = None

#------------------------------------------------------------------------------ 

class UDPSession(automat.Automat):
    """
    This class implements all the functionality of the ``udp_session()`` state machine.
    """

    timers = {
        'timer-1min': (60, ['CONNECTED']),
        'timer-1sec': (1.0, ['PING','GREETING']),
        'timer-30sec': (30.0, ['GREETING']),
        'timer-10sec': (10.0, ['PING','CONNECTED']),
        }
    
    def __init__(self, node, peer_address, peer_id=None):
        self.node = node
        self.peer_address = peer_address
        self.peer_id = peer_id
        self.peer_idurl = None
        self.last_datagram_received_time = 0
        self.bytes_sent = 0
        self.bytes_received = 0
        self.file_queue = udp_file_queue.FileQueue(self) 
        name = 'udp_session[%s:%d]' % (self.peer_address[0], self.peer_address[1])
        automat.Automat.__init__(self, name, 'AT_STARTUP')

    def send_packet(self, command, payload):
        self.bytes_sent += len(payload)
        return udp.send_command(self.node.listen_port, command, 
                                payload, self.peer_address)

    def A(self, event, arg):
        #---CONNECTED---
        if self.state == 'CONNECTED':
            if event == 'datagram-received' :
                self.doReceiveData(arg)
            elif event == 'timer-10sec' :
                self.doAlive(arg)
            elif event == 'shutdown' or ( event == 'timer-1min' and not self.isSessionActive(arg) ) :
                self.state = 'CLOSED'
                self.doNotifyDisconnected(arg)
                self.doDestroyMe(arg)
        #---AT_STARTUP---
        elif self.state == 'AT_STARTUP':
            if event == 'init' :
                self.state = 'PING'
                self.doInit(arg)
                self.doPing(arg)
            elif event == 'shutdown' :
                self.state = 'CLOSED'
                self.doDestroyMe(arg)
        #---PING---
        elif self.state == 'PING':
            if event == 'timer-1sec' :
                self.doPing(arg)
            elif event == 'datagram-received' and self.isPing(arg) :
                self.state = 'GREETING'
                self.doReceiveData(arg)
            elif event == 'datagram-received' and self.isGreeting(arg) :
                self.state = 'GREETING'
                self.doReceiveData(arg)
            elif event == 'datagram-received' and not self.isPingOrGreeting(arg) :
                self.doReceiveData(arg)
            elif event == 'shutdown' or event == 'timer-10sec' :
                self.state = 'CLOSED'
                self.doDestroyMe(arg)
        #---GREETING---
        elif self.state == 'GREETING':
            if event == 'timer-1sec' :
                self.doGreeting(arg)
            elif event == 'shutdown' or event == 'timer-30sec' :
                self.state = 'CLOSED'
                self.doDestroyMe(arg)
            elif event == 'datagram-received' and not self.isGreetingOrAlive(arg) :
                self.doReceiveData(arg)
            elif event == 'datagram-received' and self.isGreetingOrAlive(arg) :
                self.state = 'CONNECTED'
                self.doReceiveData(arg)
                self.doNotifyConnected(arg)
                self.doCheckPendingFiles(arg)
        #---CLOSED---
        elif self.state == 'CLOSED':
            pass

    def isPing(self, arg):
        """
        Condition method.
        """
        command = arg[0][0]
        return command == udp.CMD_PING

    def isGreeting(self, arg):
        """
        Condition method.
        """
        command = arg[0][0]
        return command == udp.CMD_GREETING

    def isPingOrGreeting(self, arg):
        """
        Condition method.
        """
        command = arg[0][0]
        return ( command == udp.CMD_PING or command == udp.CMD_GREETING)

    def isGreetingOrAlive(self, arg):
        """
        Condition method.
        """
        command = arg[0][0]
        return ( command == udp.CMD_ALIVE or command == udp.CMD_GREETING)

    def isSessionActive(self, arg):
        """
        Condition method.
        """
        return time.time() - self.last_datagram_received_time < 60

    def doInit(self, arg):
        """
        Action method.
        """
        # self.listen_port, self.my_id, self.my_address = arg

    def doAlive(self, arg):
        """
        Action method.
        """
        udp.send_command(self.node.listen_port, udp.CMD_ALIVE, '', self.peer_address)

    def doGreeting(self, arg):
        """
        Action method.
        """
        payload = str(self.node.my_id)+' '+str(self.node.my_idurl)
        udp.send_command(self.node.listen_port, udp.CMD_GREETING, payload, self.peer_address)

    def doPing(self, arg):
        """
        Action method.
        """
        udp.send_command(self.node.listen_port, udp.CMD_PING, '', self.peer_address)

    def doReceiveData(self, arg):
        """
        Action method.
        """
        self.last_datagram_received_time = time.time()
        try:
            datagram, address = arg
            command, payload = datagram
        except:
            return
        assert address == self.peer_address
        self.bytes_received += len(payload)
        if command == udp.CMD_DATA:
            self.file_queue.on_received_data_packet(payload)
        elif command == udp.CMD_ACK:
            self.file_queue.on_received_ack_packet(payload)
        if command == udp.CMD_GREETING:
            try:
                new_peer_id, new_peer_idurl = payload.split(' ')
            except:
                return 
            udp.send_command(self.node.listen_port, udp.CMD_ALIVE, '', self.peer_address)
            if self.peer_id:
                if new_peer_id != self.peer_id:
                    lg.out(4, 'udp_session.doReceiveData WARNING session: %s,  peer_id from GREETING is different: %s' % (self, new_peer_id))
            else:
                # lg.out(4, 'udp_session.doReceiveData got peer id (%s) for session %s from GREETING packet' % (new_peer_id, self))
                self.peer_id = new_peer_id
            if self.peer_idurl:
                if new_peer_idurl != self.peer_idurl:
                    lg.out(4, 'udp_session.doReceiveData WARNING session: %s,  peer_idurl from GREETING is different: %s' % (self, new_peer_idurl))
            else:
                # lg.out(4, 'udp_session.doReceiveData got peer idurl (%s) for session %s from GREETING packet' % (new_peer_id, self))
                self.peer_idurl = new_peer_idurl
            for s in sessions().values():
                if self.id == s.id:
                    continue
                if self.peer_id == s.peer_id:
                    lg.out(6, 'udp_session.doReceiveData WARNING  got GREETING from another address, close session %s' % s)
                    s.automat('shutdown')
                    continue
                if self.peer_idurl == s.peer_idurl:
                    lg.out(6, 'udp_session.doReceiveData WARNING  got GREETING from another idurl, close session %s' % s)
                    s.automat('shutdown')
                    continue
        elif command == udp.CMD_PING:
            payload = str(self.node.my_id)+' '+str(self.node.my_idurl)
            udp.send_command(self.node.listen_port, udp.CMD_GREETING, payload, self.peer_address)

    def doNotifyConnected(self, arg):
        """
        Action method.
        """
        # print 'CONNECTED!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'

    def doNotifyDisconnected(self, arg):
        """
        Action method.
        """
        # print 'DISCONNECTED!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!'

    def doCheckPendingFiles(self, arg):
        """
        Action method.
        """
        global _PendingOutboxFiles
        i = 0
        while i < len(_PendingOutboxFiles):
            filename, host, description, result_defer, single, tm = _PendingOutboxFiles.pop(i)
            if host == self.peer_id:
                self.file_queue.append_outbox_file(filename, description, result_defer, single)
            else:
                _PendingOutboxFiles.insert(i, (filename, host, description, result_defer, single, tm))
                i += 1

    def doDestroyMe(self, arg):
        """
        Action method.
        """
        self.file_queue.close()
        self.file_queue = None
        self.node = None
        sessions().pop(self.id)
        automat.objects().pop(self.index)


