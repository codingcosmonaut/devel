#!/usr/bin/python
# api.py
#
# Copyright (C) 2008 Veselin Penev, https://bitdust.io
#
# This file (api.py) is part of BitDust Software.
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
#
#
#
#

"""
.. module:: api.

Here is a bunch of methods to interact with BitDust software.
"""

#------------------------------------------------------------------------------

from __future__ import absolute_import

#------------------------------------------------------------------------------

_Debug = True
_DebugLevel = 8

_APILogFileEnabled = None

#------------------------------------------------------------------------------

import os
import sys
import time
import gc

from twisted.internet import reactor  # @UnresolvedImport
from twisted.internet.defer import Deferred  # @UnresolvedImport
from twisted.python.failure import Failure  # @UnresolvedImport

#------------------------------------------------------------------------------

from lib import strng
from lib import jsn

from logs import lg

from services import driver

from main import config

#------------------------------------------------------------------------------


def on_api_result_prepared(result):
    # TODO
    return result

#------------------------------------------------------------------------------


def OK(result='', message=None, status='OK', **kwargs):
    global _APILogFileEnabled
    o = {'status': status, }
    if result:
        if isinstance(result, dict):
            o['result'] = result
        else:
            o['result'] = result if isinstance(result, list) else [result, ]
    if message is not None:
        o['message'] = message
    o = on_api_result_prepared(o)
    sample = ''
    if _Debug or _APILogFileEnabled:
        try:
            sample = jsn.dumps(o, ensure_ascii=True, sort_keys=True)
        except:
            lg.exc()
            sample = strng.to_text(o, errors='ignore')
    api_method = kwargs.get('api_method', None)
    if not api_method:
        api_method = sys._getframe().f_back.f_code.co_name
        if api_method.count('lambda') or api_method.startswith('_'):
            api_method = sys._getframe(1).f_back.f_code.co_name
    if _Debug:
        if api_method not in [
            'process_health',
            'network_connected',
        ] or _DebugLevel > 10:
            lg.out(_DebugLevel, 'api.%s return OK(%s)' % (api_method, sample[:150]))
    if _APILogFileEnabled is None:
        _APILogFileEnabled = config.conf().getBool('logs/api-enabled')
    if _APILogFileEnabled:
        lg.out(0, 'api.%s return OK(%s)\n' % (api_method, sample, ), log_name='api', showtime=True)
    return o


def RESULT(result=[], message=None, status='OK', errors=None, source=None, extra_fields=None, **kwargs):
    global _APILogFileEnabled
    o = {}
    if source is not None:
        o.update(source)
    o.update({'status': status, 'result': result})
    if message is not None:
        o['message'] = message
    if errors is not None:
        o['errors'] = errors
    if extra_fields is not None:
        o.update(extra_fields)
    o = on_api_result_prepared(o)
    sample = ''
    if _Debug or _APILogFileEnabled:
        try:
            sample = jsn.dumps(o, ensure_ascii=True, sort_keys=True)
        except:
            lg.exc()
            sample = strng.to_text(o, errors='ignore')
    api_method = kwargs.get('api_method', None)
    if not api_method:
        api_method = sys._getframe().f_back.f_code.co_name
        if api_method.count('lambda') or api_method.startswith('_'):
            api_method = sys._getframe(1).f_back.f_code.co_name
    if _Debug:
        lg.out(_DebugLevel, 'api.%s return RESULT(%s)' % (api_method, sample[:150], ))
    if _APILogFileEnabled is None:
        _APILogFileEnabled = config.conf().getBool('logs/api-enabled')
    if _APILogFileEnabled:
        lg.out(0, 'api.%s return RESULT(%s)\n' % (api_method, sample, ), log_name='api', showtime=True)
    return o


def ERROR(errors=[], message=None, status='ERROR', reason=None, details=None, **kwargs):
    global _APILogFileEnabled
    if not isinstance(errors, list):
        errors = [errors, ]
    for i in range(len(errors)):
        if isinstance(errors[i], Failure):
            try:
                errors[i] = errors[i].getErrorMessage()
            except:
                errors[i] = 'unknown failure'
        else:
            try:
                errors[i] = strng.to_text(errors[i])
            except:
                errors[i] = 'unknown exception'
    o = {'status': status, 'errors': errors, }
    if message is not None:
        o['message'] = message
    if reason is not None:
        o['reason'] = reason
    if details is not None:
        o.update(details)
    o = on_api_result_prepared(o)
    sample = ''
    if _Debug or _APILogFileEnabled:
        try:
            sample = jsn.dumps(o, ensure_ascii=True, sort_keys=True)
        except:
            lg.exc()
            sample = strng.to_text(o, errors='ignore')
    api_method = kwargs.get('api_method', None)
    if not api_method:
        api_method = sys._getframe().f_back.f_code.co_name
        if api_method.count('lambda') or api_method.startswith('_'):
            api_method = sys._getframe(1).f_back.f_code.co_name
    if _Debug:
        lg.out(_DebugLevel, 'api.%s return ERROR(%s)' % (api_method, sample[:150], ))
    if _APILogFileEnabled is None:
        _APILogFileEnabled = config.conf().getBool('logs/api-enabled')
    if _APILogFileEnabled:
        lg.out(0, 'api.%s return ERROR(%s)\n' % (api_method, sample, ), log_name='api', showtime=True)
    return o

#------------------------------------------------------------------------------


def process_stop():
    """
    Stop the main process immediately.

    ###### HTTP
        curl -X GET 'localhost:8180/process/stop/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "process_stop", "kwargs": {} }');
    """
    if _Debug:
        lg.out(_DebugLevel, 'api.process_stop sending event "stop" to the shutdowner() machine')
    from main import shutdowner
    reactor.callLater(0.1, shutdowner.A, 'stop', 'exit')  # @UndefinedVariable
    # shutdowner.A('stop', 'exit')
    return OK('stopped')


def process_restart():
    """
    Restart the main process.

    ###### HTTP
        curl -X GET 'localhost:8180/process/restart/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "process_restart", "kwargs": {} }');
    """
    from main import shutdowner
    # if showgui:
    #     if _Debug:
    #         lg.out(_DebugLevel, 'api.process_restart sending event "stop" to the shutdowner() machine')
    #     reactor.callLater(0.1, shutdowner.A, 'stop', 'restartnshow')  # @UndefinedVariable
    #     # shutdowner.A('stop', 'restartnshow')
    #     return OK({'restarted': True, 'show_gui': True, })
    if _Debug:
        lg.out(_DebugLevel, 'api.process_restart sending event "stop" to the shutdowner() machine')
    # shutdowner.A('stop', 'restart')
    reactor.callLater(0.1, shutdowner.A, 'stop', 'restart')  # @UndefinedVariable
    return OK({'restarted': True, })


def process_health():
    """
    Returns positive response if engine process is running. This method suppose to be used for health checks.

    ###### HTTP
        curl -X GET 'localhost:8180/process/health/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "process_health", "kwargs": {} }');
    """
    return OK()


def process_debug():
    """
    Execute a breakpoint inside the main thread and start Python shell using standard `pdb.set_trace()` debugger method.

    This is only useful if you already have executed the BitDust engine manually via shell console and would like
    to interrupt it and investigate things.

    This call will block the main process and it will stop responding to any API calls.

    ###### HTTP
        curl -X GET 'localhost:8180/process/debug/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "process_debug", "kwargs": {} }');
    """
    import pdb
    pdb.set_trace()
    return OK()

#------------------------------------------------------------------------------

def config_get(key):
    """
    Returns current key/value from the program settings.

    ###### HTTP
        curl -X GET 'localhost:8180/config/get/v1?key=logs/debug-level'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "config_get", "kwargs": {"key": "logs/debug-level"} }');
    """
    try:
        key = strng.to_text(key).strip('/')
    except:
        return ERROR('wrong key')
    if _Debug:
        lg.out(_DebugLevel, 'api.config_get [%s]' % key)
    if key and not config.conf().exist(key):
        return ERROR('option "%s" not exist' % key)

    if key and not config.conf().hasChilds(key):
        return RESULT([config.conf().toJson(key), ], )
    childs = []
    for child in config.conf().listEntries(key):
        if config.conf().hasChilds(child):
            childs.append({
                'key': child,
                'childs': len(config.conf().listEntries(child)),
            })
        else:
            childs.append(config.conf().toJson(child))
    return RESULT(childs)


def config_set(key, value):
    """
    Set a value for given key option.

    ###### HTTP
        curl -X POST 'localhost:8180/config/set/v1' -d '{"key": "logs/debug-level", "value": 12}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "config_set", "kwargs": {"key": "logs/debug-level", "value": 12} }');
    """
    key = strng.to_text(key)
    v = {}
    if config.conf().exist(key):
        v['old_value'] = config.conf().getValueOfType(key)
    typ_label = config.conf().getTypeLabel(key)
    if _Debug:
        lg.out(_DebugLevel, 'api.config_set [%s]=%s type is %s' % (key, value, typ_label))
    config.conf().setValueOfType(key, value)
    v.update(config.conf().toJson(key))
    return RESULT([v, ])


def configs_list(sort=False):
    """
    Provide detailed info about all program settings.

    ###### HTTP
        curl -X GET 'localhost:8180/config/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "configs_list", "kwargs": {} }');
    """
    if _Debug:
        lg.out(_DebugLevel, 'api.configs_list')
    r = config.conf().cache()
    r = [config.conf().toJson(key) for key in list(r.keys())]
    if sort:
        r = sorted(r, key=lambda i: i['key'])
    return RESULT(r)


def configs_tree():
    """
    Returns all options as a tree structure, can be more suitable for UI operations.

    ###### HTTP
        curl -X GET 'localhost:8180/config/tree/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "configs_tree", "kwargs": {} }');
    """
    if _Debug:
        lg.out(_DebugLevel, 'api.configs_tree')
    r = {}
    for key in config.conf().cache():
        cursor = r
        for part in key.split('/'):
            if part not in cursor:
                cursor[part] = {}
            cursor = cursor[part]
        cursor.update(config.conf().toJson(key))
    return RESULT([r, ])

#------------------------------------------------------------------------------

def identity_get(include_xml_source=False):
    """
    Returns your identity info.

    ###### HTTP
        curl -X GET 'localhost:8180/identity/get/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "identity_get", "kwargs": {} }');
    """
    from userid import my_id
    if not my_id.isLocalIdentityReady():
        return ERROR('local identity is not valid or not exist')
    r = my_id.getLocalIdentity().serialize_json()
    if include_xml_source:
        r['xml'] = my_id.getLocalIdentity().serialize(as_text=True)
    return OK(r)


def identity_create(username, preferred_servers=[]):
    """
    Generates new private key and creates new identity for you to be able to communicate with other nodes in the network.

    Parameter `username` defines filename of the new identity.

    ###### HTTP
        curl -X POST 'localhost:8180/identity/create/v1' -d '{"username": "alice"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "identity_create", "kwargs": {"username": "alice"} }');
    """
    from lib import misc
    from userid import my_id
    from userid import id_registrator
    if my_id.isLocalIdentityReady() or my_id.isLocalIdentityExists():
        return ERROR('local identity already exist')
    try:
        username = strng.to_text(username)
    except:
        return ERROR('invalid user name')
    if not misc.ValidUserName(username):
        return ERROR('invalid user name')

    ret = Deferred()
    my_id_registrator = id_registrator.A()

    def _id_registrator_state_changed(oldstate, newstate, event_string, *args, **kwargs):
        if _Debug:
            lg.args(_DebugLevel, oldstate=oldstate, newstate=newstate, event_string=event_string)
        if ret.called:
            return
        if oldstate != newstate and newstate == 'FAILED':
            ret.callback(ERROR(my_id_registrator.last_message, api_method='identity_create'))
            return
        if oldstate != newstate and newstate == 'DONE':
            my_id.loadLocalIdentity()
            if not my_id.isLocalIdentityReady():
                return ERROR('identity creation failed, please try again later', api_method='identity_create')
            r = my_id.getLocalIdentity().serialize_json()
            r['xml'] = my_id.getLocalIdentity().serialize(as_text=True)
            ret.callback(OK(r, api_method='identity_create'))
            return

    my_id_registrator.addStateChangedCallback(_id_registrator_state_changed)
    my_id_registrator.A('start', username=username, preferred_servers=preferred_servers)
    return ret


def identity_backup(destination_filepath):
    """
    Creates local file at `destination_filepath` on your disk drive with a backup copy of your private key and recent IDURL.

    You can use that file to restore identity in case of lost data using `identity_recover()` API method.

    WARNING! Make sure to always have a backup copy of your identity secret key in a safe place - there is no other way
    to restore your data in case of lost.

    ###### HTTP
        curl -X POST 'localhost:8180/identity/backup/v1' -d '{"destination_filepath": "/tmp/alice_backup.key"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "identity_backup", "kwargs": {"destination_filepath": "/tmp/alice_backup.key"} }');
    """
    from userid import my_id
    from crypt import key
    from system import bpio
    if not my_id.isLocalIdentityReady():
        return ERROR('local identity is not ready')
    TextToSave = ''
    for id_source in my_id.getLocalIdentity().getSources(as_originals=True):
        TextToSave += strng.to_text(id_source) + u'\n'
    TextToSave += key.MyPrivateKey()
    if not bpio.WriteTextFile(destination_filepath, TextToSave):
        del TextToSave
        gc.collect()
        return ERROR('error writing to %s\n' % destination_filepath)
    del TextToSave
    gc.collect()
    return OK(message='WARNING! keep your master key in a safe place and never ever publish it anywhere!')


def identity_recover(private_key_source, known_idurl=None):
    """
    Restores your identity from backup copy.

    Input parameter `private_key_source` must contain your latest IDURL and the private key as openssh formated string.

    ###### HTTP
        curl -X POST 'localhost:8180/identity/recover/v1' -d '{"private_key_source": "http://some-host.com/alice.xml\n-----BEGIN RSA PRIVATE KEY-----\nMIIEogIBAAKC..."}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "identity_recover", "kwargs": {"private_key_source": "http://some-host.com/alice.xml\n-----BEGIN RSA PRIVATE KEY-----\nMIIEogIBAAKC..."} }');
    """
    from userid import my_id
    from userid import id_url
    from userid import id_restorer
    if my_id.isLocalIdentityReady() or my_id.isLocalIdentityExists():
        return ERROR('local identity already exist')
    if not private_key_source:
        return ERROR('must provide private key in order to recover your identity')
    if len(private_key_source) > 1024 * 10:
        return ERROR('private key is too large')
    idurl_list = []
    pk_source = ''
    try:
        lines = private_key_source.split('\n')
        for i in range(len(lines)):
            line = lines[i]
            if not line.startswith('-----BEGIN RSA PRIVATE KEY-----'):
                idurl_list.append(id_url.field(line))
                continue
            pk_source = '\n'.join(lines[i:])
            break
    except:
        idurl_list = []
        pk_source = private_key_source
    if not idurl_list and known_idurl:
        idurl_list.append(known_idurl)
    if not idurl_list:
        return ERROR('you must provide at least one IDURL address of your identity')

    ret = Deferred()
    my_id_restorer = id_restorer.A()

    def _id_restorer_state_changed(oldstate, newstate, event_string, *args, **kwargs):
        if _Debug:
            lg.args(_DebugLevel, oldstate=oldstate, newstate=newstate, event_string=event_string)
        if ret.called:
            return
        if newstate == 'FAILED':
            ret.callback(ERROR(my_id_restorer.last_message, api_method='identity_recover'))
            return
        if newstate == 'RESTORED!':
            my_id.loadLocalIdentity()
            if not my_id.isLocalIdentityReady():
                return ERROR('identity recovery FAILED', api_method='identity_recover')
            r = my_id.getLocalIdentity().serialize_json()
            r['xml'] = my_id.getLocalIdentity().serialize(as_text=True)
            ret.callback(OK(r, api_method='identity_recover'))
            return

    try:
        my_id_restorer.addStateChangedCallback(_id_restorer_state_changed)
        my_id_restorer.A('start', {'idurl': idurl_list[0], 'keysrc': pk_source, })
        # TODO: iterate over idurl_list to find at least one reliable source
    except Exception as exc:
        lg.exc()
        ret.callback(ERROR(exc, api_method='identity_recover'))
    return ret


def identity_erase(erase_private_key=False):
    """
    Method will erase current identity file and the private key (optionally).
    All network services will be stopped first.

    ###### HTTP
        curl -X DELETE 'localhost:8180/identity/erase/v1' -d '{"erase_private_key": true}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "identity_erase", "kwargs": {"erase_private_key": true} }');
    """
    return ERROR('not implemented yet. please manually stop the application process and erase files inside ".bitdust/metadata/" folder')


def identity_rotate():
    """
    Rotate your identity sources and republish identity file on another ID server even if current ID servers are healthy.

    Normally that procedure is executed automatically when current process detects unhealthy ID server among your identity sources.

    This method is provided for testing and development purposes.

    ###### HTTP
        curl -X PUT 'localhost:8180/identity/rotate/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "identity_rotate", "kwargs": {} }');
    """
    from userid import my_id
    if not my_id.isLocalIdentityReady():
        return ERROR('local identity is not ready')
    from p2p import id_rotator
    old_sources = my_id.getLocalIdentity().getSources(as_originals=True)
    ret = Deferred()
    d = id_rotator.run(force=True)

    def _cb(result):
        if not result:
            ret.callback(ERROR(result, api_method='identity_rotate'))
            return None
        r = my_id.getLocalIdentity().serialize_json()
        r['old_sources'] = old_sources
        ret.callback(OK(r, api_method='identity_rotate'))
        return None

    def _eb(e):
        ret.callback(ERROR(e, api_method='identity_rotate'))
        return None

    d.addCallback(_cb)
    d.addErrback(_eb)
    return ret


def identity_cache_list():
    """
    Returns list of all cached locally identity files received from other users.

    ###### HTTP
        curl -X GET 'localhost:8180/identity/cache/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "identity_cache_list", "kwargs": {} }');
    """
    from contacts import identitycache
    results = []
    for id_obj in identitycache.Items().values():
        r = id_obj.serialize_json()
        results.append(r)
    results.sort(key=lambda r: r['name'])
    return RESULT(results)

#------------------------------------------------------------------------------

def key_get(key_id, include_private=False):
    """
    Returns details of the registered public or private key.

    Use `include_private=True` if you also need a private key (as openssh formated string) to be present in the response.

    ###### HTTP
        curl -X GET 'localhost:8180/key/get/v1?key_id=abcd1234$alice@server-a.com'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "key_get", "kwargs": {"key_id": "abcd1234$alice@server-a.com"} }');
    """
    if not driver.is_on('service_keys_registry'):
        return ERROR('service_keys_registry() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.key_get')
    from crypt import my_keys
    try:
        key_info = my_keys.get_key_info(key_id=key_id, include_private=include_private)
        key_info.pop('include_private', None)
    except Exception as exc:
        return ERROR(exc)
    return OK(key_info)


def keys_list(sort=False, include_private=False):
    """
    List details for all registered public and private keys.

    Use `include_private=True` if you also need a private key (as openssh formated string) to be present in the response.

    ###### HTTP
        curl -X GET 'localhost:8180/key/list/v1?include_private=1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "keys_list", "kwargs": {"include_private": 1} }');
    """
    if not driver.is_on('service_keys_registry'):
        return ERROR('service_keys_registry() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.keys_list')
    from crypt import my_keys
    r = []
    for key_id, key_object in my_keys.known_keys().items():
        if not key_object:
            key_object = my_keys.key_obj(key_id)
        key_alias, creator_idurl = my_keys.split_key_id(key_id)
        if not key_alias or not creator_idurl:
            lg.warn('incorrect key_id: %s' % key_id)
            continue
        try:
            key_info = my_keys.make_key_info(key_object, key_id=key_id, include_private=include_private)
        except:
            key_info = my_keys.make_key_info(key_object, key_id=key_id, include_private=False)
        key_info.pop('include_private', None)
        r.append(key_info)
    if sort:
        r = sorted(r, key=lambda i: i['alias'])
    r.insert(0, my_keys.make_master_key_info(include_private=include_private))
    return RESULT(r)


def key_create(key_alias, key_size=None, label='', include_private=False):
    """
    Generate new RSA private key and add it to the list of registered keys with a new `key_id`.

    Optional input parameter `key_size` can be 1024, 2048, 4096. If `key_size` was not passed, default value will be
    populated from the `personal/private-key-size` program setting.

    Parameter `label` can be used to attach some meaningful information for the user to display in the UI.

    Use `include_private=True` if you also need a private key (as openssh formated string) to be present in the response.

    ###### HTTP
        curl -X POST 'localhost:8180/key/create/v1' -d '{"key_alias": "abcd1234", "key_size": 1024, "label": "Cats and Dogs"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "key_create", "kwargs": {"key_alias": "abcd1234", "key_size": 1024, "label": "Cats and Dogs"} }');
    """
    if not driver.is_on('service_keys_registry'):
        return ERROR('service_keys_registry() is not started')
    from lib import utime
    from crypt import my_keys
    from main import settings
    from userid import my_id
    key_alias = strng.to_text(key_alias)
    key_alias = key_alias.strip().lower()
    key_id = my_keys.make_key_id(key_alias, creator_idurl=my_id.getLocalID())
    if not my_keys.is_valid_key_id(key_id):
        return ERROR('key "%s" is not valid' % key_id)
    if my_keys.is_key_registered(key_id):
        return ERROR('key "%s" already exist' % key_id)
    if not key_size:
        key_size = settings.getPrivateKeySize()
    if _Debug:
        lg.out(_DebugLevel, 'api.key_create id=%s, size=%s' % (key_id, key_size))
    if not label:
        label = 'share%s' % utime.make_timestamp()
    key_object = my_keys.generate_key(key_id, label=label, key_size=key_size)
    if key_object is None:
        return ERROR('failed to generate private key "%s"' % key_id)
    key_info = my_keys.make_key_info(
        key_object,
        key_id=key_id,
        include_private=include_private
    )
    key_info.pop('include_private', None)
    return OK(key_info, message='new private key "%s" was generated successfully' % key_alias, )


def key_label(key_id, label):
    """
    Set new label for the given key.

    ###### HTTP
        curl -X POST 'localhost:8180/key/label/v1' -d '{"key_id": "abcd1234$alice@server-a.com", "label": "Man and Woman"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "key_label", "kwargs": {"key_id": "abcd1234$alice@server-a.com", "label": "Man and Woman"} }');
    """
    if not driver.is_on('service_keys_registry'):
        return ERROR('service_keys_registry() is not started')
    from crypt import my_keys
    from userid import my_id
    key_label = strng.to_text(label)
    if not my_keys.is_valid_key_id(key_id):
        return ERROR('key "%s" is not valid' % key_id)
    if not my_keys.is_key_registered(key_id):
        return ERROR('key "%s" not exist' % key_id)
    if key_id == 'master' or key_id == my_id.getGlobalID(key_alias='master') or key_id == my_id.getGlobalID():
        return ERROR('master key label can not be changed')
    if _Debug:
        lg.out(_DebugLevel, 'api.key_label id=%s, label=%r' % (key_id, key_label))
    my_keys.key_obj(key_id).label = label
    if not my_keys.save_key(key_id):
        return ERROR('key "%s" store failed' % key_id)
    return OK(message='key "%s" label updated successfully' % key_id)


def key_erase(key_id):
    """
    Unregister and remove given key from the list of known keys and erase local file.

    ###### HTTP
        curl -X DELETE 'localhost:8180/key/erase/v1' -d '{"key_id": "abcd1234$alice@server-a.com"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "key_erase", "kwargs": {"key_id": "abcd1234$alice@server-a.com"} }');
    """
    if not driver.is_on('service_keys_registry'):
        return ERROR('service_keys_registry() is not started')
    from crypt import my_keys
    key_id = strng.to_text(key_id)
    if _Debug:
        lg.out(_DebugLevel, 'api.keys_list')
    if key_id == 'master':
        return ERROR('"master" key can not be erased')
    key_alias, creator_idurl = my_keys.split_key_id(key_id)
    if not key_alias or not creator_idurl:
        return ERROR('incorrect key_id format')
    if not my_keys.erase_key(key_id):
        return ERROR('failed to erase private key "%s"' % key_id)
    return OK(message='private key "%s" was erased successfully' % key_id)


def key_share(key_id, trusted_user_id, include_private=False, timeout=10):
    """
    Connects to remote user and transfer given public or private key to that node.
    This way you can share access to files/groups/resources with other users in the network.

    If you pass `include_private=True` also private part of the key will be shared, otherwise only public part.

    ###### HTTP
        curl -X PUT 'localhost:8180/key/share/v1' -d '{"key_id": "abcd1234$alice@server-a.com", "trusted_user_id": "bob@machine-b.net"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "key_share", "kwargs": {"key_id": "abcd1234$alice@server-a.com", "trusted_user_id": "bob@machine-b.net"} }');
    """
    from userid import global_id
    try:
        trusted_user_id = strng.to_text(trusted_user_id)
        full_key_id = strng.to_text(key_id)
    except:
        return ERROR('error reading input parameters')
    if not driver.is_on('service_keys_registry'):
        return ERROR('service_keys_registry() is not started')
    glob_id = global_id.ParseGlobalID(full_key_id)
    if glob_id['key_alias'] == 'master':
        return ERROR('"master" key can not be shared')
    if not glob_id['key_alias'] or not glob_id['idurl']:
        return ERROR('incorrect key_id format')
    idurl = strng.to_bin(trusted_user_id)
    if global_id.IsValidGlobalUser(idurl):
        idurl = global_id.GlobalUserToIDURL(idurl, as_field=False)
    from access import key_ring
    ret = Deferred()
    d = key_ring.share_key(key_id=full_key_id, trusted_idurl=idurl, include_private=include_private, timeout=timeout)
    d.addCallback(lambda resp: ret.callback(OK(strng.to_text(resp), api_method='key_share')))
    d.addErrback(lambda err: ret.callback(ERROR(err, api_method='key_share')))
    return ret


def key_audit(key_id, untrusted_user_id, is_private=False, timeout=10):
    """
    Connects to remote node identified by `untrusted_user_id` parameter and request audit of given public or private key `key_id` on that node.

    Returns positive result if audit process succeed - that means remote user really possess the key.

    ###### HTTP
        curl -X POST 'localhost:8180/key/audit/v1' -d '{"key_id": "abcd1234$alice@server-a.com", "untrusted_user_id": "carol@computer-c.net", "is_private": 1}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "key_audit", "kwargs": {"key_id": "abcd1234$alice@server-a.com", "untrusted_user_id": "carol@computer-c.net", "is_private": 1} }');
    """
    from userid import global_id
    try:
        untrusted_user_id = strng.to_text(untrusted_user_id)
        full_key_id = strng.to_text(key_id)
    except:
        return ERROR('error reading input parameters')
    if not driver.is_on('service_keys_registry'):
        return ERROR('service_keys_registry() is not started')
    glob_id = global_id.ParseGlobalID(full_key_id)
    if not glob_id['key_alias'] or not glob_id['idurl']:
        return ERROR('incorrect key_id format')
    if global_id.IsValidGlobalUser(untrusted_user_id):
        idurl = global_id.GlobalUserToIDURL(untrusted_user_id, as_field=False)
    else:
        idurl = strng.to_bin(untrusted_user_id)
    from access import key_ring
    ret = Deferred()
    if is_private:
        d = key_ring.audit_private_key(key_id=key_id, untrusted_idurl=idurl, timeout=timeout)
    else:
        d = key_ring.audit_public_key(key_id=key_id, untrusted_idurl=idurl, timeout=timeout)
    d.addCallback(lambda resp: ret.callback(OK(strng.to_text(resp), api_method='key_audit')))
    d.addErrback(lambda err: ret.callback(ERROR(err, api_method='key_audit')))
    return ret

#------------------------------------------------------------------------------

def files_sync():
    """
    This should re-start "data synchronization" process with your remote suppliers.

    Normally all communications and synchronizations are handled automatically, so you do not need to
    call that method.

    This method is provided for testing and development purposes.

    ###### HTTP
        curl -X GET 'localhost:8180/file/sync/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "files_sync", "kwargs": {} }');
    """
    if not driver.is_on('service_backups'):
        return ERROR('service_backups() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.files_sync')
    from storage import backup_monitor
    backup_monitor.A('restart')
    if _Debug:
        lg.out(_DebugLevel, 'api.files_sync')
    return OK('the main files sync loop has been restarted')


def files_list(remote_path=None, key_id=None, recursive=True, all_customers=False,
               include_uploads=False, include_downloads=False, ):
    """
    Returns list of known files registered in the catalog under given `remote_path` folder.
    By default returns items from root of the catalog.

    If `key_id` is passed will only return items encrypted using that key.

    Use `all_customers=True` to get list of all registered files - including received/shared to you by another user.

    You can also use `include_uploads` and `include_downloads` parameters to get more info about currently running
    uploads and downloads.

    ###### HTTP
        curl -X GET 'localhost:8180/file/list/v1?remote_path=abcd1234$alice@server-a.com:pictures/cats/'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "files_list", "kwargs": {"remote_path": "abcd1234$alice@server-a.com:pictures/cats/"} }');
    """
    if not driver.is_on('service_backup_db'):
        return ERROR('service_backup_db() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.files_list remote_path=%s key_id=%s recursive=%s all_customers=%s include_uploads=%s include_downloads=%s' % (
            remote_path, key_id, recursive, all_customers, include_uploads, include_downloads, ))
    from storage import backup_fs
    from storage import backup_control
    from system import bpio
    from lib import misc
    from userid import global_id
    from crypt import my_keys
    result = []
    glob_path = global_id.ParseGlobalID(remote_path)
    norm_path = global_id.NormalizeGlobalID(glob_path.copy())
    remotePath = bpio.remotePath(norm_path['path'])
    customer_idurl = norm_path['idurl']
    if not all_customers and customer_idurl not in backup_fs.known_customers():
        return ERROR('customer "%s" not found' % customer_idurl)
    if all_customers:
        lookup = []
        for customer_idurl in backup_fs.known_customers():
            look = backup_fs.ListChildsByPath(
                path=remotePath,
                recursive=recursive,
                iter=backup_fs.fs(customer_idurl),
                iterID=backup_fs.fsID(customer_idurl),
            )
            if isinstance(look, list):
                lookup.extend(look)
            else:
                lg.warn(look)
    else:
        lookup = backup_fs.ListChildsByPath(
            path=remotePath,
            recursive=recursive,
            iter=backup_fs.fs(customer_idurl),
            iterID=backup_fs.fsID(customer_idurl),
        )
    if not isinstance(lookup, list):
        return ERROR(lookup)
    for i in lookup:
        # if not i['item']['k']:
        #     i['item']['k'] = my_id.getGlobalID(key_alias='master')
        if i['path_id'] == 'index':
            continue
        if key_id is not None and key_id != i['item']['k']:
            continue
        if glob_path['key_alias'] and i['item']['k']:
            if i['item']['k'] != my_keys.make_key_id(alias=glob_path['key_alias'], creator_glob_id=glob_path['customer']):
                continue
        key_alias = 'master'
        if i['item']['k']:
            real_key_id = i['item']['k']
            key_alias, real_idurl = my_keys.split_key_id(real_key_id)
            real_customer_id = global_id.UrlToGlobalID(real_idurl)
        else:
            real_key_id = my_keys.make_key_id(alias='master', creator_idurl=customer_idurl)
            real_idurl = customer_idurl
            real_customer_id = global_id.UrlToGlobalID(customer_idurl)
        full_glob_id = global_id.MakeGlobalID(path=i['path_id'], customer=real_customer_id, key_alias=key_alias, )
        full_remote_path = global_id.MakeGlobalID(path=i['path'], customer=real_customer_id, key_alias=key_alias, )
        r = {
            'remote_path': full_remote_path,
            'global_id': full_glob_id,
            'customer': real_customer_id,
            'idurl': real_idurl,
            'path_id': i['path_id'],
            'name': i['name'],
            'path': i['path'],
            'type': backup_fs.TYPES.get(i['type'], '').lower(),
            'size': i['total_size'],
            'local_size': i['item']['s'],
            'latest': i['latest'],
            'key_id': real_key_id,
            'key_alias': key_alias,
            'childs': i['childs'],
            'versions': i['versions'],
            'uploads': {
                'running': [],
                'pending': [],
            },
            'downloads': [],
        }
        if include_uploads:
            backup_control.tasks()
            running = []
            for backupID in backup_control.FindRunningBackup(pathID=full_glob_id):
                j = backup_control.jobs().get(backupID)
                if j:
                    running.append({
                        'backup_id': j.backupID,
                        'key_id': j.keyID,
                        'source_path': j.sourcePath,
                        'eccmap': j.eccmap.name,
                        'pipe': 'closed' if not j.pipe else j.pipe.state(),
                        'block_size': j.blockSize,
                        'aborting': j.ask4abort,
                        'terminating': j.terminating,
                        'eof_state': j.stateEOF,
                        'reading': j.stateReading,
                        'closed': j.closed,
                        'work_blocks': len(j.workBlocks),
                        'block_number': j.blockNumber,
                        'bytes_processed': j.dataSent,
                        'progress': misc.percent2string(j.progress()),
                        'total_size': j.totalSize,
                    })
            pending = []
            t = backup_control.GetPendingTask(full_glob_id)
            if t:
                pending.append({
                    'task_id': t.number,
                    'path_id': t.pathID,
                    'source_path': t.localPath,
                    'created': time.asctime(time.localtime(t.created)),
                })
            r['uploads']['running'] = running
            r['uploads']['pending'] = pending
        if include_downloads:
            from storage import restore_monitor
            downloads = []
            for backupID in restore_monitor.FindWorking(pathID=full_glob_id):
                d = restore_monitor.GetWorkingRestoreObject(backupID)
                if d:
                    downloads.append({
                        'backup_id': d.backup_id,
                        'creator_id': d.creator_id,
                        'path_id': d.path_id,
                        'version': d.version,
                        'block_number': d.block_number,
                        'bytes_processed': d.bytes_written,
                        'created': time.asctime(time.localtime(d.Started)),
                        'aborted': d.abort_flag,
                        'done': d.done_flag,
                        'eccmap': '' if not d.EccMap else d.EccMap.name,
                    })
            r['downloads'] = downloads
        result.append(r)        
    if _Debug:
        lg.out(_DebugLevel, '    %d items returned' % len(result))
    return RESULT(result, extra_fields={
        'revision': backup_control.revision(),
    })


def file_exists(remote_path):
    """
    Returns positive result if file or folder with such `remote_path` already exists in the catalog.

    ###### HTTP
        curl -X GET 'localhost:8180/file/exists/v1?remote_path=abcd1234$alice@server-a.com:pictures/cats/pussy.png'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "file_exists", "kwargs": {"remote_path": "abcd1234$alice@server-a.com:pictures/cats/pussy.png"} }');
    """
    if not driver.is_on('service_backup_db'):
        return ERROR('service_backup_db() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.file_exists remote_path=%s' % remote_path)
    from storage import backup_fs
    from system import bpio
    from userid import global_id
    glob_path = global_id.ParseGlobalID(remote_path)
    norm_path = global_id.NormalizeGlobalID(glob_path.copy())
    remotePath = bpio.remotePath(norm_path['path'])
    customer_idurl = norm_path['idurl']
    if customer_idurl not in backup_fs.known_customers():
        return OK({'exist': False, 'path_id': None, }, message='customer "%s" not found' % customer_idurl, )
    pathID = backup_fs.ToID(remotePath, iter=backup_fs.fs(customer_idurl))
    if not pathID:
        return OK({'exist': False, 'path_id': None, }, message='path "%s" was not found in catalog' % remotePath, )
    item = backup_fs.GetByID(pathID, iterID=backup_fs.fsID(customer_idurl))
    if not item:
        return OK({'exist': False, 'path_id': None, }, message='item "%s" is not found in catalog' % pathID, )
    return OK({'exist': True, 'path_id': pathID, }, )


def file_info(remote_path, include_uploads=True, include_downloads=True):
    """
    Returns detailed info about given file or folder in the catalog.

    You can also use `include_uploads` and `include_downloads` parameters to get more info about currently running
    uploads and downloads.

    ###### HTTP
        curl -X GET 'localhost:8180/file/info/v1?remote_path=abcd1234$alice@server-a.com:pictures/dogs/bobby.jpeg'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "file_info", "kwargs": {"remote_path": "abcd1234$alice@server-a.com:pictures/dogs/bobby.jpeg"} }');
    """
    if not driver.is_on('service_backup_db'):
        return ERROR('service_backup_db() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.file_info remote_path=%s include_uploads=%s include_downloads=%s' % (
            remote_path, include_uploads, include_downloads))
    from storage import backup_fs
    from lib import misc
    from lib import packetid
    from system import bpio
    from userid import global_id
    glob_path = global_id.ParseGlobalID(remote_path)
    norm_path = global_id.NormalizeGlobalID(glob_path.copy())
    remotePath = bpio.remotePath(norm_path['path'])
    customer_idurl = norm_path['idurl']
    if customer_idurl not in backup_fs.known_customers():
        return ERROR('customer "%s" not found' % customer_idurl)
    pathID = backup_fs.ToID(remotePath, iter=backup_fs.fs(customer_idurl))
    if not pathID:
        return ERROR('path "%s" was not found in catalog' % remotePath)
    item = backup_fs.GetByID(pathID, iterID=backup_fs.fsID(customer_idurl))
    if not item:
        return ERROR('item "%s" is not found in catalog' % pathID)
    (item_size, item_time, versions) = backup_fs.ExtractVersions(pathID, item)  # , customer_id=norm_path['customer'])
    glob_path_item = norm_path.copy()
    glob_path_item['path'] = pathID
    key_alias = 'master'
    if item.key_id:
        key_alias = packetid.KeyAlias(item.key_id)
    r = {
        'remote_path': global_id.MakeGlobalID(
            path=norm_path['path'], customer=norm_path['customer'], key_alias=key_alias,),
        'global_id': global_id.MakeGlobalID(
            path=pathID,
            customer=norm_path['customer'],
            key_alias=key_alias, ),
        'customer': norm_path['customer'],
        'path_id': pathID,
        'path': remotePath,
        'type': backup_fs.TYPES.get(item.type, '').lower(),
        'size': item_size,
        'latest': item_time,
        'key_id': item.key_id,
        'versions': versions,
        'uploads': {
            'running': [],
            'pending': [],
        },
        'downloads': [],
    }
    if include_uploads:
        from storage import backup_control
        backup_control.tasks()
        running = []
        for backupID in backup_control.FindRunningBackup(pathID=pathID):
            j = backup_control.jobs().get(backupID)
            if j:
                running.append({
                    'backup_id': j.backupID,
                    'key_id': j.keyID,
                    'source_path': j.sourcePath,
                    'eccmap': j.eccmap.name,
                    'pipe': 'closed' if not j.pipe else j.pipe.state(),
                    'block_size': j.blockSize,
                    'aborting': j.ask4abort,
                    'terminating': j.terminating,
                    'eof_state': j.stateEOF,
                    'reading': j.stateReading,
                    'closed': j.closed,
                    'work_blocks': len(j.workBlocks),
                    'block_number': j.blockNumber,
                    'bytes_processed': j.dataSent,
                    'progress': misc.percent2string(j.progress()),
                    'total_size': j.totalSize,
                })
        pending = []
        t = backup_control.GetPendingTask(pathID)
        if t:
            pending.append({
                'task_id': t.number,
                'path_id': t.pathID,
                'source_path': t.localPath,
                'created': time.asctime(time.localtime(t.created)),
            })
        r['uploads']['running'] = running
        r['uploads']['pending'] = pending
    if include_downloads:
        from storage import restore_monitor
        downloads = []
        for backupID in restore_monitor.FindWorking(pathID=pathID):
            d = restore_monitor.GetWorkingRestoreObject(backupID)
            if d:
                downloads.append({
                    'backup_id': d.backup_id,
                    'creator_id': d.creator_id,
                    'path_id': d.path_id,
                    'version': d.version,
                    'block_number': d.block_number,
                    'bytes_processed': d.bytes_written,
                    'created': time.asctime(time.localtime(d.Started)),
                    'aborted': d.abort_flag,
                    'done': d.done_flag,
                    'eccmap': '' if not d.EccMap else d.EccMap.name,
                })
        r['downloads'] = downloads
    if _Debug:
        lg.out(_DebugLevel, 'api.file_info : "%s"' % pathID)
    return RESULT([r, ], extra_fields={
        'revision': backup_control.revision(),
    })


def file_create(remote_path, as_folder=False, exist_ok=False, force_path_id=None):
    """
    Creates new file in the catalog, but do not upload any data to the network yet.

    This method only creates a "virtual ID" for the new data.

    Pass `as_folder=True` to create a virtual folder instead of a file.

    ###### HTTP
        curl -X POST 'localhost:8180/file/create/v1' -d '{"remote_path": "abcd1234$alice@server-a.com:movies/travels/safari.mp4"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "file_create", "kwargs": {"remote_path": "abcd1234$alice@server-a.com:movies/travels/safari.mp4"} }');
    """
    if not driver.is_on('service_backup_db'):
        return ERROR('service_backup_db() is not started')
    from storage import backup_fs
    from storage import backup_control
    from system import bpio
    from main import control
    from userid import global_id
    from crypt import my_keys
    parts = global_id.NormalizeGlobalID(global_id.ParseGlobalID(remote_path))
    if not parts['path']:
        return ERROR('invalid "remote_path" format')
    path = bpio.remotePath(parts['path'])
    customer_idurl = parts['idurl']
    pathID = backup_fs.ToID(path, iter=backup_fs.fs(customer_idurl))
    keyID = my_keys.make_key_id(alias=parts['key_alias'], creator_glob_id=parts['customer'])
    keyAlias = parts['key_alias']
    if _Debug:
        lg.args(_DebugLevel, remote_path=remote_path, as_folder=as_folder, path_id=pathID, customer_idurl=customer_idurl, force_path_id=force_path_id)
    if pathID is not None:
        if exist_ok:
            fullRemotePath = global_id.MakeGlobalID(customer=parts['customer'], path=parts['path'], key_alias=keyAlias)
            fullGlobID = global_id.MakeGlobalID(customer=parts['customer'], path=pathID, key_alias=keyAlias)
            return OK({
                'path_id': pathID,
                'key_id': keyID,
                'path': path,
                'remote_path': fullRemotePath,
                'global_id': fullGlobID,
                'customer': customer_idurl,
                'created': False,
                'type': ('dir' if as_folder else 'file'),
            }, message='remote path "%s" already exist in catalog: "%s"' % (('folder' if as_folder else 'file'), fullGlobID), )
        return ERROR('remote path "%s" already exist in catalog: "%s"' % (path, pathID))
    if as_folder:
        newPathID, _, _ = backup_fs.AddDir(
            path,
            read_stats=False,
            iter=backup_fs.fs(customer_idurl),
            iterID=backup_fs.fsID(customer_idurl),
            key_id=keyID,
            force_path_id=force_path_id,
        )
    else:
        parent_path = os.path.dirname(path)
        if not backup_fs.IsDir(parent_path, iter=backup_fs.fs(customer_idurl)):
            if backup_fs.IsFile(parent_path, iter=backup_fs.fs(customer_idurl)):
                return ERROR('remote path can not be assigned, file already exist: "%s"' % parent_path)
            parentPathID, _, _ = backup_fs.AddDir(
                parent_path,
                read_stats=False,
                iter=backup_fs.fs(customer_idurl),
                iterID=backup_fs.fsID(customer_idurl),
                key_id=keyID,
            )
            if _Debug:
                lg.out(_DebugLevel, 'api.file_create parent folder "%s" was created at "%s"' % (parent_path, parentPathID))
        id_iter_iterID = backup_fs.GetIteratorsByPath(
            parent_path,
            iter=backup_fs.fs(customer_idurl),
            iterID=backup_fs.fsID(customer_idurl),
        )
        if not id_iter_iterID:
            return ERROR('remote path can not be assigned, parent folder not found: "%s"' % parent_path)
        parentPathID = id_iter_iterID[0]
        newPathID, _, _ = backup_fs.PutItem(
            name=os.path.basename(path),
            parent_path_id=parentPathID,
            as_folder=as_folder,
            iter=id_iter_iterID[1],
            iterID=id_iter_iterID[2],
            key_id=keyID,
        )
        if not newPathID:
            return ERROR('remote path can not be assigned, failed to create a new item: "%s"' % path)
    backup_control.Save()
    control.request_update([('pathID', newPathID), ])
    full_glob_id = global_id.MakeGlobalID(customer=parts['customer'], path=newPathID, key_alias=keyAlias)
    full_remote_path = global_id.MakeGlobalID(customer=parts['customer'], path=parts['path'], key_alias=keyAlias)
    if _Debug:
        lg.out(_DebugLevel, 'api.file_create : "%s"' % full_glob_id)
    return OK({
        'path_id': newPathID,
        'key_id': keyID,
        'path': path,
        'remote_path': full_remote_path,
        'global_id': full_glob_id,
        'customer': parts['idurl'],
        'created': True,
        'type': ('dir' if as_folder else 'file'),
    }, message='new %s created in "%s"' % (('folder' if as_folder else 'file'), full_glob_id), )


def file_delete(remote_path):
    """
    Removes virtual file or folder from the catalog and also notifies your remote suppliers to clean up corresponding uploaded data.

    ###### HTTP
        curl -X POST 'localhost:8180/file/delete/v1' -d '{"remote_path": "abcd1234$alice@server-a.com:cars/ferrari.gif"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "file_delete", "kwargs": {"remote_path": "abcd1234$alice@server-a.com:cars/ferrari.gif"} }');
    """
    if not driver.is_on('service_backup_db'):
        return ERROR('service_backup_db() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.file_delete remote_path=%s' % remote_path)
    from storage import backup_fs
    from storage import backup_control
    from storage import backup_monitor
    from main import settings
    from main import control
    from lib import packetid
    from system import bpio
    from userid import global_id
    parts = global_id.NormalizeGlobalID(global_id.ParseGlobalID(remote_path))
    if not parts['idurl'] or not parts['path']:
        return ERROR('invalid "remote_path" format')
    path = bpio.remotePath(parts['path'])
    pathID = backup_fs.ToID(path, iter=backup_fs.fs(parts['idurl']))
    if not pathID:
        return ERROR('remote path "%s" was not found' % parts['path'])
    if not packetid.Valid(pathID):
        return ERROR('invalid item found: "%s"' % pathID)
    pathIDfull = packetid.MakeBackupID(parts['customer'], pathID)
    keyAlias = parts['key_alias'] or 'master'
    full_glob_id = global_id.MakeGlobalID(customer=parts['customer'], path=pathID, key_alias=keyAlias)
    full_remote_path = global_id.MakeGlobalID(customer=parts['customer'], path=parts['path'], key_alias=keyAlias)
    result = backup_control.DeletePathBackups(pathID=pathIDfull, saveDB=False, calculate=False)
    if not result:
        return ERROR('remote item "%s" was not found' % pathIDfull)
    backup_fs.DeleteLocalDir(settings.getLocalBackupsDir(), pathIDfull)
    backup_fs.DeleteByID(pathID, iter=backup_fs.fs(parts['idurl']), iterID=backup_fs.fsID(parts['idurl']))
    backup_fs.Scan()
    backup_fs.Calculate()
    backup_control.Save()
    backup_monitor.A('restart')
    control.request_update([('pathID', pathIDfull), ])
    if _Debug:
        lg.out(_DebugLevel, 'api.file_delete %s' % parts)
    return OK({
        'path_id': pathIDfull,
        'path': path,
        'remote_path': full_remote_path,
        'global_id': full_glob_id,
        'customer': parts['idurl'],
    }, message='item "%s" was deleted from remote suppliers' % pathIDfull, )


def files_uploads(include_running=True, include_pending=True):
    """
    Returns a list of currently running uploads and list of pending items to be uploaded.

    ###### HTTP
        curl -X GET 'localhost:8180/file/upload/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "files_uploads", "kwargs": {} }');
    """
    if not driver.is_on('service_backups'):
        return ERROR('service_backups() is not started')
    from lib import misc
    from storage import backup_control
    if _Debug:
        lg.out(_DebugLevel, 'api.file_uploads include_running=%s include_pending=%s' % (include_running, include_pending, ))
        lg.out(_DebugLevel, '     %d jobs running, %d tasks pending' % (
            len(backup_control.jobs()), len(backup_control.tasks())))
    r = {'running': [], 'pending': [], }
    if include_running:
        r['running'].extend([{
            'version': j.backupID,
            'key_id': j.keyID,
            'source_path': j.sourcePath,
            'eccmap': j.eccmap.name,
            'pipe': 'closed' if not j.pipe else j.pipe.state(),
            'block_size': j.blockSize,
            'aborting': j.ask4abort,
            'terminating': j.terminating,
            'eof_state': j.stateEOF,
            'reading': j.stateReading,
            'closed': j.closed,
            'work_blocks': len(j.workBlocks),
            'block_number': j.blockNumber,
            'bytes_processed': j.dataSent,
            'progress': misc.percent2string(j.progress()),
            'total_size': j.totalSize,
        } for j in backup_control.jobs().values()])
    if include_pending:
        r['pending'].extend([{
            'task_id': t.number,
            'path_id': t.pathID,
            'source_path': t.localPath,
            'created': time.asctime(time.localtime(t.created)),
        } for t in backup_control.tasks()])
    return RESULT(r)


def file_upload_start(local_path, remote_path, wait_result=False, open_share=False):
    """
    Starts a new file or folder (including all sub-folders and files) upload from `local_path` on your disk drive
    to the virtual location `remote_path` in the catalog. New "version" of the data will be created for given catalog item
    and uploading task started.

    You can use `wait_result=True` to block the response from that method until uploading finishes or fails (makes no sense for large uploads).

    Parameter `open_share` can be useful if you uploading data into a "shared" virtual path using another key that shared to you.

    ###### HTTP
        curl -X POST 'localhost:8180/file/upload/start/v1' -d '{"remote_path": "abcd1234$alice@server-a.com:cars/fiat.jpeg", "local_path": "/tmp/fiat.jpeg"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "file_upload_start", "kwargs": {"remote_path": "abcd1234$alice@server-a.com:cars/fiat.jpeg", "local_path": "/tmp/fiat.jpeg"} }');
    """
    if not driver.is_on('service_backups'):
        return ERROR('service_backups() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.file_upload_start local_path=%s remote_path=%s wait_result=%s open_share=%s' % (
            local_path, remote_path, wait_result, open_share, ))
    from system import bpio
    from storage import backup_fs
    from storage import backup_control
    from lib import packetid
    from main import control
    from userid import global_id
    from crypt import my_keys
    if not bpio.pathExist(local_path):
        return ERROR('local file or folder "%s" not exist' % local_path)
    parts = global_id.NormalizeGlobalID(remote_path)
    if not parts['idurl'] or not parts['path']:
        return ERROR('invalid "remote_path" format')
    if parts['key_alias'] == 'master':
        is_hidden_item = parts['path'].startswith('.')
        if not is_hidden_item:
            if not driver.is_on('service_my_data'):
                return ERROR('service_my_data() is not started')
    path = bpio.remotePath(parts['path'])
    pathID = backup_fs.ToID(path, iter=backup_fs.fs(parts['idurl']))
    if not pathID:
        return ERROR('path "%s" not registered yet' % remote_path)
    keyID = my_keys.make_key_id(alias=parts['key_alias'], creator_glob_id=parts['customer'])
    customerID = global_id.MakeGlobalID(customer=parts['customer'], key_alias=parts['key_alias'])
    pathIDfull = packetid.MakeBackupID(customerID, pathID)
    if open_share and parts['key_alias'] != 'master':
        if not driver.is_on('service_shared_data'):
            return ERROR('service_shared_data() is not started')
        from access import shared_access_coordinator
        active_share = shared_access_coordinator.get_active_share(keyID)
        if not active_share:
            active_share = shared_access_coordinator.SharedAccessCoordinator(
                keyID, log_events=True, publish_events=False, )
        if active_share.state != 'CONNECTED':
            active_share.automat('restart')
    if wait_result:
        d = Deferred()
        tsk = backup_control.StartSingle(
            pathID=pathIDfull,
            localPath=local_path,
            keyID=keyID,
        )
        tsk.result_defer.addCallback(lambda result: d.callback(OK(
            {
                'remote_path': remote_path,
                'version': result[0],
                'key_id': tsk.keyID,
                'source_path': local_path,
                'path_id': pathID,
            },
            message='item "%s" uploaded, local path is: "%s"' % (remote_path, local_path),
            api_method='file_upload_start',
        )))
        tsk.result_defer.addErrback(lambda result: d.callback(ERROR(
            'upload task %d for "%s" failed: %s' % (tsk.number, tsk.pathID, result[1], ),
            api_method='file_upload_start',
        )))
        backup_fs.Calculate()
        backup_control.Save()
        control.request_update([('pathID', pathIDfull), ])
        if _Debug:
            lg.out(_DebugLevel, 'api.file_upload_start %s with %s, wait_result=True' % (remote_path, pathIDfull))
        return d
    tsk = backup_control.StartSingle(
        pathID=pathIDfull,
        localPath=local_path,
        keyID=keyID,
    )
    # tsk.result_defer.addCallback(lambda result: lg.dbg(
    #     'callback from api.file_upload_start.task(%s) done with %s' % (result[0], result[1], )))
    tsk.result_defer.addErrback(lambda result: lg.err(
        'errback from api.file_upload_start.task(%s) failed with %s' % (result[0], result[1], )))
    backup_fs.Calculate()
    backup_control.Save()
    control.request_update([('pathID', pathIDfull), ])
    if _Debug:
        lg.out(_DebugLevel, 'api.file_upload_start %s with %s' % (remote_path, pathIDfull))
    return OK(
        {
            'remote_path': remote_path,
            'key_id': tsk.keyID,
            'source_path': local_path,
            'path_id': pathID,
        },
        message='uploading "%s" started, local path is: "%s"' % (remote_path, local_path),
    )


def file_upload_stop(remote_path):
    """
    Useful method if you need to interrupt and cancel already running uploading task.

    ###### HTTP
        curl -X POST 'localhost:8180/file/upload/stop/v1' -d '{"remote_path": "abcd1234$alice@server-a.com:cars/fiat.jpeg"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "file_upload_stop", "kwargs": {"remote_path": "abcd1234$alice@server-a.com:cars/fiat.jpeg"} }');
    """
    if not driver.is_on('service_backups'):
        return ERROR('service_backups() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.file_upload_stop remote_path=%s' % remote_path)
    from storage import backup_control
    from storage import backup_fs
    from system import bpio
    from userid import global_id
    from lib import packetid
    parts = global_id.NormalizeGlobalID(global_id.ParseGlobalID(remote_path))
    if not parts['idurl'] or not parts['path']:
        return ERROR('invalid "remote_path" format')
    remotePath = bpio.remotePath(parts['path'])
    pathID = backup_fs.ToID(remotePath, iter=backup_fs.fs(parts['idurl']))
    if not pathID:
        return ERROR('remote path "%s" was not found' % parts['path'])
    if not packetid.Valid(pathID):
        return ERROR('invalid item found: "%s"' % pathID)
    pathIDfull = packetid.MakeBackupID(parts['customer'], pathID)
    r = []
    msg = []
    if backup_control.AbortPendingTask(pathIDfull):
        r.append(pathIDfull)
        msg.append('pending item "%s" removed' % pathIDfull)
    for backupID in backup_control.FindRunningBackup(pathIDfull):
        if backup_control.AbortRunningBackup(backupID):
            r.append(backupID)
            msg.append('backup "%s" aborted' % backupID)
    if not r:
        return ERROR('no running or pending tasks for "%s" found' % pathIDfull)
    if _Debug:
        lg.out(_DebugLevel, 'api.file_upload_stop %s' % r)
    return RESULT(r, message=(', '.join(msg)))


def files_downloads():
    """
    Returns a list of currently running downloading tasks.

    ###### HTTP
        curl -X GET 'localhost:8180/file/download/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "files_downloads", "kwargs": {} }');
    """
    if not driver.is_on('service_backups'):
        return ERROR('service_backups() is not started')
    from storage import restore_monitor
    if _Debug:
        lg.out(_DebugLevel, 'api.files_downloads')
        lg.out(_DebugLevel, '    %d items downloading at the moment' % len(restore_monitor.GetWorkingObjects()))
    return RESULT([{
        'backup_id': r.backup_id,
        'creator_id': r.creator_id,
        'path_id': r.path_id,
        'version': r.version,
        'block_number': r.block_number,
        'bytes_processed': r.bytes_written,
        'created': time.asctime(time.localtime(r.Started)),
        'aborted': r.abort_flag,
        'done': r.done_flag,
        'key_id': r.key_id,
        'eccmap': '' if not r.EccMap else r.EccMap.name,
    } for r in restore_monitor.GetWorkingObjects()])


def file_download_start(remote_path, destination_path=None, wait_result=False, open_share=True):
    """
    Download data from remote suppliers to your local machine.

    You can use different methods to select the target data with `remote_path` input:

      + "virtual" path of the file
      + internal path ID in the catalog
      + full data version identifier with path ID and version name

    It is possible to select the destination folder to extract requested files to.
    By default this method uses specified value from `paths/restore` program setting or user home folder.

    You can use `wait_result=True` to block the response from that method until downloading finishes or fails (makes no sense for large files).

    WARNING! Your existing local data in `destination_path` will be overwritten!

    ###### HTTP
        curl -X POST 'localhost:8180/file/download/start/v1' -d '{"remote_path": "abcd1234$alice@server-a.com:movies/back_to_the_future.mp4", "local_path": "/tmp/films/"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "file_download_start", "kwargs": {"remote_path": "abcd1234$alice@server-a.com:movies/back_to_the_future.mp4", "local_path": "/tmp/films/"} }');
    """
    if not driver.is_on('service_restores'):
        return ERROR('service_restores() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.file_download_start remote_path=%s destination_path=%s wait_result=%s open_share=%s' % (
            remote_path, destination_path, wait_result, open_share, ))
    from storage import backup_fs
    from storage import backup_control
    from storage import restore_monitor
    from main import control
    from system import bpio
    from lib import packetid
    from main import settings
    from userid import my_id
    from userid import global_id
    from crypt import my_keys
    glob_path = global_id.NormalizeGlobalID(global_id.ParseGlobalID(remote_path))
    if glob_path['key_alias'] == 'master':
        is_hidden_item = glob_path['path'].startswith('.')
        if not is_hidden_item:
            if not driver.is_on('service_my_data'):
                return ERROR('service_my_data() is not started')
    else:
        if not driver.is_on('service_shared_data'):
            return ERROR('service_shared_data() is not started')
    if packetid.Valid(glob_path['path']):
        _, pathID, version = packetid.SplitBackupID(remote_path)
        if not pathID and version:
            pathID, version = version, ''
        item = backup_fs.GetByID(pathID, iterID=backup_fs.fsID(glob_path['customer']))
        if not item:
            return ERROR('path "%s" is not found in catalog' % remote_path)
        if not version:
            version = item.get_latest_version()
        if not version:
            return ERROR('not found any remote versions for "%s"' % remote_path)
        key_alias = 'master'
        if item.key_id:
            key_alias = packetid.KeyAlias(item.key_id)
        customerGlobalID = global_id.MakeGlobalID(customer=glob_path['customer'], key_alias=key_alias)
        backupID = packetid.MakeBackupID(customerGlobalID, pathID, version)
    else:
        remotePath = bpio.remotePath(glob_path['path'])
        knownPathID = backup_fs.ToID(remotePath, iter=backup_fs.fs(glob_path['idurl']))
        if not knownPathID:
            return ERROR('path "%s" was not found in catalog' % remotePath)
        item = backup_fs.GetByID(knownPathID, iterID=backup_fs.fsID(glob_path['idurl']))
        if not item:
            return ERROR('item "%s" is not found in catalog' % knownPathID)
        version = glob_path['version']
        if not version:
            version = item.get_latest_version()
        if not version:
            return ERROR('not found any remote versions for "%s"' % remote_path)
        key_alias = 'master'
        if item.key_id:
            key_alias = packetid.KeyAlias(item.key_id)
        customerGlobalID = global_id.MakeGlobalID(customer=glob_path['customer'], key_alias=key_alias)
        backupID = packetid.MakeBackupID(customerGlobalID, knownPathID, version)
    if backup_control.IsBackupInProcess(backupID):
        return ERROR('download not possible, uploading "%s" is in process' % backupID)
    if restore_monitor.IsWorking(backupID):
        return ERROR('downloading task for "%s" already scheduled' % backupID)
    customerGlobalID, pathID_target, version = packetid.SplitBackupID(backupID)
    if not customerGlobalID:
        customerGlobalID = global_id.UrlToGlobalID(my_id.getLocalID())
    knownPath = backup_fs.ToPath(pathID_target, iterID=backup_fs.fsID(global_id.GlobalUserToIDURL(customerGlobalID)))
    if not knownPath:
        return ERROR('location "%s" not found in catalog' % knownPath)
    if not destination_path:
        destination_path = settings.getRestoreDir()
    if not destination_path:
        destination_path = settings.DefaultRestoreDir()
    key_id = my_keys.make_key_id(alias=glob_path['key_alias'], creator_glob_id=glob_path['customer'])
    ret = Deferred()
        
    def _on_result(backupID, result):
        if result == 'restore done':
            ret.callback(OK(
                {
                    'downloaded': True,
                    'key_id': key_id,
                    'backup_id': backupID,
                    'local_path': destination_path,
                    'path_id': pathID_target,
                    'remote_path': knownPath,
                },
                message='version "%s" downloaded to "%s"' % (backupID, destination_path),
                api_method='file_download_start'
            ))
        else:
            ret.callback(ERROR(
                'downloading version "%s" failed, result: %s' % (backupID, result),
                details={
                    'downloaded': False,
                    'key_id': key_id,
                    'backup_id': backupID,
                    'local_path': destination_path,
                    'path_id': pathID_target,
                    'remote_path': knownPath,
                },
                api_method='file_download_start',
            ))
        return True

    def _start_restore():
        if _Debug:
            lg.out(_DebugLevel, 'api.file_download_start._start_restore %s to %s, wait_result=%s' % (
                backupID, destination_path, wait_result))
        if wait_result:
            restore_monitor.Start(backupID, destination_path, keyID=key_id, callback=_on_result)
            control.request_update([('pathID', knownPath), ])
            return ret
        restore_monitor.Start(backupID, destination_path, keyID=key_id, )
        control.request_update([('pathID', knownPath), ])
        ret.callback(OK(
            {
                'downloaded': False,
                'key_id': key_id,
                'backup_id': backupID,
                'local_path': destination_path,
                'path_id': pathID_target,
                'remote_path': knownPath,
            },
            message='downloading of version "%s" has been started to "%s"' % (backupID, destination_path),
            api_method='file_download_start',
        ))
        return True

    def _on_share_connected(active_share, callback_id, result):
        if _Debug:
            lg.out(_DebugLevel, 'api.download_start._on_share_connected callback_id=%s result=%s' % (callback_id, result, ))
        if not result:
            if _Debug:
                lg.out(_DebugLevel, '    share %s is now DISCONNECTED, removing callback %s' % (active_share.key_id, callback_id,))
            active_share.remove_connected_callback(callback_id)
            ret.callback(ERROR(
                'downloading version "%s" failed, result: %s' % (backupID, 'share is disconnected'),
                details={
                    'key_id': active_share.key_id,
                    'backup_id': backupID,
                    'local_path': destination_path,
                    'path_id': pathID_target,
                    'remote_path': knownPath,
                },
            ))
            return True
        if _Debug:
            lg.out(_DebugLevel, '        share %s is now CONNECTED, removing callback %s and starting restore process' % (
                active_share.key_id, callback_id,))
        reactor.callLater(0, active_share.remove_connected_callback, callback_id)  # @UndefinedVariable
        _start_restore()
        return True

    def _open_share():
        if not driver.is_on('service_shared_data'):
            ret.callback(ERROR('service_shared_data() is not started'))
            return False
        from access import shared_access_coordinator
        active_share = shared_access_coordinator.get_active_share(key_id)
        if not active_share:
            active_share = shared_access_coordinator.SharedAccessCoordinator(
                key_id=key_id,
                log_events=True,
                publish_events=False,
            )
            if _Debug:
                lg.out(_DebugLevel, 'api.download_start._open_share opened new share : %s' % active_share.key_id)
        else:
            if _Debug:
                lg.out(_DebugLevel, 'api.download_start._open_share found existing share : %s' % active_share.key_id)
        if active_share.state != 'CONNECTED':
            cb_id = 'file_download_start_' + strng.to_text(time.time())
            active_share.add_connected_callback(cb_id, lambda _id, _result: _on_share_connected(active_share, _id, _result))
            active_share.automat('restart')
            if _Debug:
                lg.out(_DebugLevel, 'api.download_start._open_share added callback %s to the active share : %s' % (cb_id, active_share.key_id))
        else:
            if _Debug:
                lg.out(_DebugLevel, 'api.download_start._open_share existing share %s is currently CONNECTED' % active_share.key_id)
            _start_restore()
        return True

    if open_share and key_alias != 'master':
        _open_share()
    else:
        if _Debug:
            lg.out(_DebugLevel, '    "open_share" skipped, starting restore')
        _start_restore()
    
    return ret


def file_download_stop(remote_path):
    """
    Abort currently running restore process.

    ###### HTTP
        curl -X POST 'localhost:8180/file/download/stop/v1' -d '{"remote_path": "abcd1234$alice@server-a.com:cars/fiat.jpeg"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "file_download_stop", "kwargs": {"remote_path": "abcd1234$alice@server-a.com:cars/fiat.jpeg"} }');
    """
    if not driver.is_on('service_restores'):
        return ERROR('service_restores() is not started')
    if _Debug:
        lg.out(_DebugLevel, 'api.file_download_stop remote_path=%s' % remote_path)
    from storage import backup_fs
    from storage import restore_monitor
    from system import bpio
    from lib import packetid
    from userid import my_id
    from userid import global_id
    glob_path = global_id.NormalizeGlobalID(global_id.ParseGlobalID(remote_path))
    backupIDs = []
    if packetid.Valid(glob_path['path']):
        customerGlobalID, pathID, version = packetid.SplitBackupID(remote_path)
        if not customerGlobalID:
            customerGlobalID = global_id.UrlToGlobalID(my_id.getLocalID())
        item = backup_fs.GetByID(pathID, iterID=backup_fs.fsID(glob_path['customer']))
        if not item:
            return ERROR('path "%s" is not found in catalog' % remote_path)
        versions = []
        if version:
            versions.append(version)
        if not versions:
            versions.extend(item.get_versions())
        for version in versions:
            backupIDs.append(packetid.MakeBackupID(customerGlobalID, pathID, version,
                                                   key_alias=glob_path['key_alias']))
    else:
        remotePath = bpio.remotePath(glob_path['path'])
        knownPathID = backup_fs.ToID(remotePath, iter=backup_fs.fs(glob_path['idurl']))
        if not knownPathID:
            return ERROR('path "%s" was not found in catalog' % remotePath)
        item = backup_fs.GetByID(knownPathID, iterID=backup_fs.fsID(glob_path['idurl']))
        if not item:
            return ERROR('item "%s" is not found in catalog' % knownPathID)
        versions = []
        if glob_path['version']:
            versions.append(glob_path['version'])
        if not versions:
            versions.extend(item.get_versions())
        for version in versions:
            backupIDs.append(packetid.MakeBackupID(glob_path['customer'], knownPathID, version,
                                                   key_alias=glob_path['key_alias']))
    if not backupIDs:
        return ERROR('not found any remote versions for "%s"' % remote_path)
    r = []
    for backupID in backupIDs:
        r.append({'backup_id': backupID, 'aborted': restore_monitor.Abort(backupID), })
    if _Debug:
        lg.out(_DebugLevel, '    stopping %s' % r)
    return RESULT(r)


def file_explore(local_path):
    """
    Useful method to be executed from the UI right after downloading is finished.

    It will open default OS file manager and display
    given `local_path` to the user so he can do something with the file.

    ###### HTTP
        curl -X GET 'localhost:8180/file/explore/v1?local_path=/tmp/movies/back_to_the_future.mp4'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "file_explore", "kwargs": {"local_path": "/tmp/movies/back_to_the_future.mp4"} }');
    """
    from lib import misc
    from system import bpio
    locpath = bpio.portablePath(local_path)
    if not bpio.pathExist(locpath):
        return ERROR('local path not exist')
    misc.ExplorePathInOS(locpath)
    return OK()

#------------------------------------------------------------------------------

def shares_list(only_active=False, include_mine=True, include_granted=True):
    """
    Returns a list of registered "shares" - encrypted locations where you can upload/download files.

    Use `only_active=True` to select only connected shares.

    Parameters `include_mine` and `include_granted` can be used to filter shares created by you,
    or by other users that shared a key with you before.

    ###### HTTP
        curl -X GET 'localhost:8180/share/list/v1?only_active=1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "shares_list", "kwargs": {"only_active": 1} }');
    """
    if not driver.is_on('service_shared_data'):
        return ERROR('service_shared_data() is not started')
    from access import shared_access_coordinator
    from crypt import my_keys
    from userid import global_id
    from userid import my_id
    results = []
    if only_active:
        for key_id in shared_access_coordinator.list_active_shares():
            _glob_id = global_id.ParseGlobalID(key_id)
            to_be_listed = False
            if include_mine and _glob_id['idurl'] == my_id.getLocalID():
                to_be_listed = True
            if include_granted and _glob_id['idurl'] != my_id.getLocalID():
                to_be_listed = True
            if not to_be_listed:
                continue
            cur_share = shared_access_coordinator.get_active_share(key_id)
            if not cur_share:
                lg.warn('share %s not found' % key_id)
                continue
            results.append(cur_share.to_json())
        return RESULT(results)
    for key_id in my_keys.known_keys():
        if not key_id.startswith('share_'):
            continue
        key_alias, creator_idurl = my_keys.split_key_id(key_id)
        to_be_listed = False
        if include_mine and creator_idurl == my_id.getLocalID():
            to_be_listed = True
        if include_granted and creator_idurl != my_id.getLocalID():
            to_be_listed = True
        if not to_be_listed:
            continue
        results.append({
            'key_id': key_id,
            'alias': key_alias,
            'label': my_keys.get_label(key_id),
            'creator': creator_idurl,
            'state': None,
            'suppliers': [],
            'ecc_map': None,
        })
    return RESULT(results)


def share_create(owner_id=None, key_size=None, label=''):
    """
    Creates a new "share" - virtual location where you or other users can upload/download files.

    This method generates a new RSA private key that will be used to encrypt and decrypt files belongs to that share.

    By default you are the owner of the new share and uploaded files will be stored by your suppliers.
    You can also use `owner_id` parameter if you wish to set another owner for that new share location.
    In that case files will be stored not on your suppliers but on his/her suppliers, if another user authorized the share.

    Optional input parameter `key_size` can be 1024, 2048, 4096. If `key_size` was not passed, default value will be
    populated from the `personal/private-key-size` program setting.

    Parameter `label` can be used to attach some meaningful information about that share location.

    ###### HTTP
        curl -X POST 'localhost:8180/share/create/v1' -d '{"label": "my summer holidays"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "share_create", "kwargs": {"label": "my summer holidays"} }');
    """
    if not driver.is_on('service_shared_data'):
        return ERROR('service_shared_data() is not started')
    from lib import utime
    from main import settings
    from crypt import key
    from crypt import my_keys
    from userid import my_id
    if not owner_id:
        owner_id = my_id.getGlobalID()
    key_id = None
    while True:
        random_sample = os.urandom(24)
        key_alias = 'share_%s' % strng.to_text(key.HashMD5(random_sample, hexdigest=True))
        key_id = my_keys.make_key_id(alias=key_alias, creator_glob_id=owner_id)
        if my_keys.is_key_registered(key_id):
            continue
        break
    if not label:
        label = 'share%s' % utime.make_timestamp()
    if not key_size:
        key_size = settings.getPrivateKeySize()
    key_object = my_keys.generate_key(key_id, label=label, key_size=key_size)
    if key_object is None:
        return ERROR('failed to generate private key "%s"' % key_id)
    key_info = my_keys.make_key_info(
        key_object,
        key_id=key_id,
        include_private=False,
    )
    key_info.pop('include_private', None)
    return OK(key_info, message='new share "%s" was generated successfully' % key_id, )


def share_delete(key_id):
    """
    Stop the active share identified by the `key_id` and erase the private key.

    ###### HTTP
        curl -X DELETE 'localhost:8180/share/delete/v1' -d '{"key_id": "share_7e9726e2dccf9ebe6077070e98e78082$alice@server-a.com"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "share_delete", "kwargs": {"key_id": "share_7e9726e2dccf9ebe6077070e98e78082$alice@server-a.com"} }');
    """
    key_id = strng.to_text(key_id)
    if not driver.is_on('service_shared_data'):
        return ERROR('service_shared_data() is not started')
    if not key_id.startswith('share_'):
        return ERROR('invalid share id')
    from access import shared_access_coordinator
    from crypt import my_keys
    this_share = shared_access_coordinator.get_active_share(key_id)
    if not this_share:
        return ERROR('share "%s" is not opened' % key_id)
    this_share.automat('shutdown')
    my_keys.erase_key(key_id)
    return OK(this_share.to_json(), message='share "%s" was deleted' % key_id, )


def share_grant(key_id, trusted_user_id, timeout=30):
    """
    Provide access to given share identified by `key_id` to another trusted user.

    This method will transfer private key to remote user `trusted_user_id` and you both will be
    able to upload/download file to the shared location.

    ###### HTTP
        curl -X PUT 'localhost:8180/share/grant/v1' -d '{"key_id": "share_7e9726e2dccf9ebe6077070e98e78082$alice@server-a.com", "trusted_user_id": "bob@machine-b.net"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "share_grant", "kwargs": {"key_id": "share_7e9726e2dccf9ebe6077070e98e78082$alice@server-a.com", "trusted_user_id": "bob@machine-b.net"} }');
    """
    if not driver.is_on('service_shared_data'):
        return ERROR('service_shared_data() is not started')
    key_id = strng.to_text(key_id)
    trusted_user_id = strng.to_text(trusted_user_id)
    if not key_id.startswith('share_'):
        return ERROR('invalid share id')
    from userid import global_id
    from userid import id_url
    trusted_user_id = strng.to_text(trusted_user_id)
    remote_idurl = None
    if trusted_user_id.count('@'):
        glob_id = global_id.ParseGlobalID(trusted_user_id)
        remote_idurl = glob_id['idurl']
    else:
        remote_idurl = id_url.field(trusted_user_id)
    if not remote_idurl:
        return ERROR('wrong user id')
    from access import shared_access_donor
    ret = Deferred()

    def _on_shared_access_donor_success(result):
        ret.callback(OK(api_method='share_grant') if result else ERROR('share grant failed', api_method='share_grant'))
        return None

    def _on_shared_access_donor_failed(err):
        ret.callback(ERROR(err))
        return None

    d = Deferred()
    d.addCallback(_on_shared_access_donor_success)
    d.addErrback(_on_shared_access_donor_failed)
    d.addTimeout(timeout, clock=reactor)
    shared_access_donor_machine = shared_access_donor.SharedAccessDonor(log_events=True, publish_events=False, )
    shared_access_donor_machine.automat('init', trusted_idurl=remote_idurl, key_id=key_id, result_defer=d)
    return ret


def share_open(key_id):
    """
    Activates given share and initiate required connections to remote suppliers to make possible to upload and download shared files.

    ###### HTTP
        curl -X PUT 'localhost:8180/share/open/v1' -d '{"key_id": "share_7e9726e2dccf9ebe6077070e98e78082$alice@server-a.com"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "share_open", "kwargs": {"key_id": "share_7e9726e2dccf9ebe6077070e98e78082$alice@server-a.com"} }');
    """
    key_id = strng.to_text(key_id)
    if not driver.is_on('service_shared_data'):
        return ERROR('service_shared_data() is not started')
    if not key_id.startswith('share_'):
        return ERROR('invalid share id')
    from access import shared_access_coordinator
    active_share = shared_access_coordinator.get_active_share(key_id)
    new_share = False
    if not active_share:
        new_share = True
        active_share = shared_access_coordinator.SharedAccessCoordinator(key_id, log_events=True, publish_events=False, )
    ret = Deferred()

    def _on_shared_access_coordinator_state_changed(oldstate, newstate, event_string, *args, **kwargs):
        if _Debug:
            lg.args(_DebugLevel, oldstate=oldstate, newstate=newstate, event_string=event_string)
        if newstate == 'CONNECTED' and oldstate != newstate:
            active_share.removeStateChangedCallback(_on_shared_access_coordinator_state_changed)
            if new_share:
                ret.callback(OK(active_share.to_json(), 'share "%s" opened' % key_id, api_method='share_open'))
            else:
                ret.callback(OK(active_share.to_json(), 'share "%s" refreshed' % key_id, api_method='share_open'))
        if newstate == 'DISCONNECTED' and oldstate != newstate:
            active_share.removeStateChangedCallback(_on_shared_access_coordinator_state_changed)
            ret.callback(ERROR('share "%s" is disconnected' % key_id, details=active_share.to_json(), api_method='share_open'))
        return None

    active_share.addStateChangedCallback(_on_shared_access_coordinator_state_changed)
    active_share.automat('restart')
    return ret


def share_close(key_id):
    """
    Disconnects and deactivate given share location.

    ###### HTTP
        curl -X PUT 'localhost:8180/share/close/v1' -d '{"key_id": "share_7e9726e2dccf9ebe6077070e98e78082$alice@server-a.com"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "share_close", "kwargs": {"key_id": "share_7e9726e2dccf9ebe6077070e98e78082$alice@server-a.com"} }');
    """
    key_id = strng.to_text(key_id)
    if not driver.is_on('service_shared_data'):
        return ERROR('service_shared_data() is not started')
    if not key_id.startswith('share_'):
        return ERROR('invalid share id')
    from access import shared_access_coordinator
    this_share = shared_access_coordinator.get_active_share(key_id)
    if not this_share:
        return ERROR('share "%s" is not opened' % key_id)
    this_share.automat('shutdown')
    return OK(this_share.to_json(), 'share "%s" closed' % key_id, )


def share_history():
    """
    Method is not implemented yet.
    """
    if not driver.is_on('service_shared_data'):
        return ERROR('service_shared_data() is not started')
    # TODO: key share history to be implemented
    # return RESULT([],)
    return ERROR('method is not implemented yet')

#------------------------------------------------------------------------------

def groups_list(only_active=False, include_mine=True, include_granted=True):
    """
    Returns a list of registered message groups.

    Use `only_active=True` to select only connected and active groups.

    Parameters `include_mine` and `include_granted` can be used to filter groups created by you,
    or by other users that shared a key with you before.

    ###### HTTP
        curl -X GET 'localhost:8180/group/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "groups_list", "kwargs": {} }');
    """
    if not driver.is_on('service_private_groups'):
        return ERROR('service_private_groups() is not started')
    from access import group_member
    from access import groups
    from crypt import my_keys
    from userid import global_id
    from userid import my_id
    results = []
    if only_active:
        for group_key_id in group_member.list_active_group_members():
            _glob_id = global_id.ParseGlobalID(group_key_id)
            to_be_listed = False
            if include_mine and _glob_id['idurl'] == my_id.getLocalID():
                to_be_listed = True
            if include_granted and _glob_id['idurl'] != my_id.getLocalID():
                to_be_listed = True
            if not to_be_listed:
                continue
            the_group = group_member.get_active_group_member(group_key_id)
            if not the_group:
                lg.warn('group %s was not found' % group_key_id)
                continue
            results.append(the_group.to_json())
        return RESULT(results)
    for group_key_id in my_keys.known_keys():
        if not group_key_id.startswith('group_'):
            continue
        group_key_alias, group_creator_idurl = my_keys.split_key_id(group_key_id)
        to_be_listed = False
        if include_mine and group_creator_idurl == my_id.getLocalID():
            to_be_listed = True
        if include_granted and group_creator_idurl != my_id.getLocalID():
            to_be_listed = True
        if not to_be_listed:
            continue
        result = {
            'group_key_id': group_key_id,
            'state': None,
            'alias': group_key_alias,
            'label': my_keys.get_label(group_key_id),
            'active': False,
        }
        result.update({'group_key_info': my_keys.get_key_info(group_key_id), })
        this_group_member = group_member.get_active_group_member(group_key_id)
        if this_group_member:
            result.update(this_group_member.to_json())
            results.append(result)
            continue
        offline_group_info = groups.known_groups().get(group_key_id)
        if offline_group_info:
            result.update(offline_group_info)
            result['state'] = 'OFFLINE'
            results.append(result)
            continue
        stored_group_info = groups.read_group_info(group_key_id)
        if stored_group_info:
            result.update(stored_group_info)
            result['state'] = 'CLOSED'
            results.append(result)
            continue
        result['state'] = 'CLEANED'
        results.append(result)
    return RESULT(results)


def group_create(creator_id=None, key_size=None, label=''):
    """
    Creates a new messaging group.

    This method generates a new RSA private key that will be used to encrypt and decrypt messages streamed thru that group.

    Optional input parameter `key_size` can be 1024, 2048, 4096. If `key_size` was not passed, default value will be
    populated from the `personal/private-key-size` program setting.

    Parameter `label` can be used to attach some meaningful information about that group.

    ###### HTTP
        curl -X POST 'localhost:8180/group/create/v1' -d '{"label": "chat with my friends"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "group_create", "kwargs": {"label": "chat with my friends"} }');
    """
    if not driver.is_on('service_private_groups'):
        return ERROR('service_private_groups() is not started')
    from main import settings
    from crypt import my_keys
    from access import groups
    from userid import my_id
    if not creator_id:
        creator_id = my_id.getGlobalID()
    if not key_size:
        key_size = settings.getPrivateKeySize()
    group_key_id = groups.create_new_group(creator_id=creator_id, label=label, key_size=key_size)
    if not group_key_id:
        return ERROR('failed to create new group')
    key_info = my_keys.get_key_info(group_key_id, include_private=False)
    key_info.pop('include_private', None)
    key_info['group_key_id'] = key_info.pop('key_id')
    ret = Deferred()
    d = groups.send_group_pub_key_to_suppliers(group_key_id)
    d.addCallback(lambda results: ret.callback(OK(key_info, message='new group "%s" was created successfully' % group_key_id)))
    d.addErrback(lambda err: ret.callback(ERROR('failed to deliver group public key to my suppliers')))
    return ret


def group_info(group_key_id):
    """
    Returns detailed info about the message group identified by `group_key_id`.

    ###### HTTP
        curl -X GET 'localhost:8180/group/info/v1?group_key_id=group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "group_info", "kwargs": {"group_key_id": "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com"} }');
    """
    if not driver.is_on('service_private_groups'):
        return ERROR('service_private_groups() is not started')
    from access import groups
    from access import group_member
    from crypt import my_keys
    group_key_id = strng.to_text(group_key_id)
    if not group_key_id.startswith('group_'):
        return ERROR('invalid group id')
    response = {
        'group_key_id': group_key_id,
        'state': None,
        'alias': my_keys.split_key_id(group_key_id)[0],
        'label': my_keys.get_label(group_key_id),
        'active': False,
    }
    if not my_keys.is_key_registered(group_key_id):
        return ERROR('group key not found')
    response.update({'group_key_info': my_keys.get_key_info(group_key_id), })
    this_group_member = group_member.get_active_group_member(group_key_id)
    if this_group_member:
        response.update(this_group_member.to_json())
        return OK(response)
    offline_group_info = groups.known_groups().get(group_key_id)
    if offline_group_info:
        response.update(offline_group_info)
        response['state'] = 'OFFLINE'
        return OK(response)
    stored_group_info = groups.read_group_info(group_key_id)
    if stored_group_info:
        response.update(stored_group_info)
        response['state'] = 'CLOSED'
        return OK(response)
    response['state'] = 'CLEANED'
    lg.warn('did not found stored group info for %r, but group key exist' % group_key_id)
    return OK(response)


def group_join(group_key_id):
    """
    Activates given messaging group to be able to receive streamed messages or send a new message to the group.

    ###### HTTP
        curl -X POST 'localhost:8180/group/join/v1' -d '{"group_key_id": "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "group_join", "kwargs": {"group_key_id": "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com"} }');
    """
    if not driver.is_on('service_private_groups'):
        return ERROR('service_private_groups() is not started')
    group_key_id = strng.to_text(group_key_id)
    if not group_key_id.startswith('group_'):
        return ERROR('invalid group id')
    from crypt import my_keys
    from userid import id_url
    if not my_keys.is_key_registered(group_key_id):
        return ERROR('unknown group key')
    ret = Deferred()
    started_group_members = []
    existing_group_members = []
    creator_idurl = my_keys.get_creator_idurl(group_key_id, as_field=False)

    def _on_group_member_state_changed(oldstate, newstate, event_string, *args, **kwargs):
        if _Debug:
            lg.args(_DebugLevel, oldstate=oldstate, newstate=newstate, event_string=event_string)
        if newstate == 'IN_SYNC!' and oldstate != newstate:
            if existing_group_members:
                existing_group_members[0].removeStateChangedCallback(_on_group_member_state_changed)
                ret.callback(OK(existing_group_members[0].to_json(), 'group "%s" refreshed' % group_key_id, api_method='group_join'))
            else:
                started_group_members[0].removeStateChangedCallback(_on_group_member_state_changed)
                ret.callback(OK(started_group_members[0].to_json(), 'group "%s" connected' % group_key_id, api_method='group_join'))
        if newstate == 'DISCONNECTED' and oldstate != newstate and oldstate != 'AT_STARTUP':
            if existing_group_members:
                existing_group_members[0].removeStateChangedCallback(_on_group_member_state_changed)
                ret.callback(ERROR('group "%s" is disconnected' % group_key_id, details=existing_group_members[0].to_json(), api_method='group_join'))
            else:
                started_group_members[0].removeStateChangedCallback(_on_group_member_state_changed)
                ret.callback(ERROR('group "%s" is disconnected' % group_key_id, details=started_group_members[0].to_json(), api_method='group_join'))
        return None

    def _do_start_group_member(): 
        from access import group_member
        existing_group_member = group_member.get_active_group_member(group_key_id)
        if _Debug:
            lg.args(_DebugLevel, existing_group_member=existing_group_member)
        if existing_group_member:
            existing_group_members.append(existing_group_member)
        else:
            existing_group_member = group_member.GroupMember(group_key_id)
            started_group_members.append(existing_group_member)
        if existing_group_member.state in ['DHT_READ?', 'BROKERS?', 'QUEUE?', 'IN_SYNC!', ]:
            connecting_word = 'active' if existing_group_member.state == 'IN_SYNC!' else 'connecting'
            ret.callback(OK(existing_group_member.to_json(), 'group "%s" already %s' % (group_key_id, connecting_word, ), api_method='group_join'))
            return None
        existing_group_member.addStateChangedCallback(_on_group_member_state_changed)
        if started_group_members:
            started_group_members[0].automat('init')
        existing_group_member.automat('join')
        return None

    def _do_cache_creator_idurl():
        from contacts import identitycache
        d = identitycache.immediatelyCaching(creator_idurl)
        d.addErrback(lambda *args: ret.callback(ERROR('failed caching group creator identity')))
        d.addCallback(lambda *args: _do_start_group_member())

    if id_url.is_cached(creator_idurl):
        _do_start_group_member()
    else:
        _do_cache_creator_idurl()
    return ret


def group_leave(group_key_id, erase_key=False):
    """
    Deactivates given messaging group. If `erase_key=True` will also erase the private key related to that group.

    ###### HTTP
        curl -X DELETE 'localhost:8180/group/leave/v1' -d '{"group_key_id": "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "group_leave", "kwargs": {"group_key_id": "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com"} }');
    """
    if not driver.is_on('service_private_groups'):
        return ERROR('service_private_groups() is not started')
    from access import group_member
    from crypt import my_keys
    group_key_id = strng.to_text(group_key_id)
    if not group_key_id.startswith('group_'):
        return ERROR('invalid group id')
    if not my_keys.is_key_registered(group_key_id):
        return ERROR('unknown group key')
    this_group_member = group_member.get_active_group_member(group_key_id)
    if not this_group_member:
        if not erase_key:
            lg.warn('active group_member() instance was not found for %r' % group_key_id)
            return ERROR('active group_member() instance was not found for %r' % group_key_id)
        my_keys.erase_key(group_key_id)
        return OK(message='group key "%s" erased' % group_key_id)
    this_group_member.automat('leave', erase_key=erase_key)
    if erase_key:
        OK(message='group "%s" deleted' % group_key_id)
    return OK(message='group "%s" deactivated' % group_key_id)


def group_share(group_key_id, trusted_user_id, timeout=30):
    """
    Provide access to given group identified by `group_key_id` to another trusted user.

    This method will transfer private key to remote user `trusted_user_id` inviting him to the messaging group.

    ###### HTTP
        curl -X PUT 'localhost:8180/group/share/v1' -d '{"group_key_id": "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com", "trusted_user_id": "bob@machine-b.net"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "group_share", "kwargs": {"key_id": "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com", "trusted_user_id": "bob@machine-b.net"} }');
    """
    if not driver.is_on('service_private_groups'):
        return ERROR('service_private_groups() is not started')
    group_key_id = strng.to_text(group_key_id)
    if not group_key_id.startswith('group_'):
        return ERROR('invalid group id')
    from userid import global_id
    from userid import id_url
    trusted_user_id = strng.to_text(trusted_user_id)
    remote_idurl = None
    if trusted_user_id.count('@'):
        glob_id = global_id.ParseGlobalID(trusted_user_id)
        remote_idurl = glob_id['idurl']
    else:
        remote_idurl = id_url.field(trusted_user_id)
    if not remote_idurl:
        return ERROR('wrong user id')
    from access import group_access_donor
    ret = Deferred()

    def _on_group_access_donor_success(result):
        ret.callback(OK( api_method='share_grant') if result else ERROR('share grant failed', api_method='group_share'))
        return None

    def _on_group_access_donor_failed(err):
        ret.callback(ERROR(err))
        return None

    d = Deferred()
    d.addCallback(_on_group_access_donor_success)
    d.addErrback(_on_group_access_donor_failed)
    d.addTimeout(timeout, clock=reactor)
    group_access_donor_machine = group_access_donor.GroupAccessDonor(log_events=True, publish_events=False, )
    group_access_donor_machine.automat('init', trusted_idurl=remote_idurl, group_key_id=group_key_id, result_defer=d)
    return ret


#------------------------------------------------------------------------------

def friends_list():
    """
    Returns list of registered correspondents.

    ###### HTTP
        curl -X GET 'localhost:8180/friend/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "friends_list", "kwargs": {} }');
    """
    from contacts import contactsdb
    from userid import global_id
    result = []
    for idurl, alias in contactsdb.correspondents():
        glob_id = global_id.ParseIDURL(idurl)
        contact_status = 'offline'
        contact_state = 'OFFLINE'
        if driver.is_on('service_identity_propagate'):
            from p2p import online_status
            if online_status.isKnown(idurl):
                contact_state = online_status.getCurrentState(idurl)
                contact_status = online_status.getStatusLabel(idurl)
            # state_machine_inst = contact_status.getInstance(idurl)
            # if state_machine_inst:
            #     contact_status_label = contact_status.stateToLabel(state_machine_inst.state)
            #     contact_state = state_machine_inst.state
        result.append({
            'idurl': idurl,
            'global_id': glob_id['customer'],
            'idhost': glob_id['idhost'],
            'username': glob_id['user'],
            'alias': alias,
            'contact_status': contact_status,
            'contact_state': contact_state,
        })
    return RESULT(result)


def friend_add(trusted_user_id, alias=''):
    """
    Add user to the list of correspondents.

    You can attach an alias to that user as a label to be displayed in the UI.

    ###### HTTP
        curl -X POST 'localhost:8180/friend/add/v1' -d '{"trusted_user_id": "dave@device-d.gov", "alias": "SuperMario"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "friend_add", "kwargs": {"trusted_user_id": "dave@device-d.gov", "alias": "SuperMario"} }');
    """
    if not driver.is_on('service_identity_propagate'):
        return ERROR('service_identity_propagate() is not started')
    from contacts import contactsdb
    from contacts import identitycache
    from main import events
    from p2p import online_status
    from userid import global_id
    from userid import id_url
    idurl = strng.to_text(trusted_user_id)
    if global_id.IsValidGlobalUser(trusted_user_id):
        idurl = global_id.GlobalUserToIDURL(trusted_user_id, as_field=False)
    idurl = id_url.field(idurl)
    if not idurl:
        return ERROR('you must specify the global IDURL address of remote user')

    def _add():
        added = False
        if not contactsdb.is_correspondent(idurl):
            contactsdb.add_correspondent(idurl, alias)
            contactsdb.save_correspondents()
            added = True
            events.send('friend-added', data=dict(
                idurl=idurl,
                global_id=global_id.idurl2glob(idurl),
                alias=alias,
            ))
        d = online_status.handshake(idurl, channel='friend_add', keep_alive=True)
        if _Debug:
            d.addErrback(lg.errback, debug=_Debug, debug_level=_DebugLevel, method='api.friend_add')
        if added:
            return OK(message='new friend has been added', api_method='friend_add')
        return OK(message='this friend has been already added', api_method='friend_add')

    if id_url.is_cached(idurl):
        return _add()

    ret = Deferred()
    d = identitycache.immediatelyCaching(idurl)
    d.addErrback(lambda *args: ret.callback(ERROR('failed caching user identity')))
    d.addCallback(lambda *args: ret.callback(_add()))
    return ret


def friend_remove(user_id):
    """
    Removes given user from the list of correspondents.

    ###### HTTP
        curl -X DELETE 'localhost:8180/friend/add/v1' -d '{"user_id": "dave@device-d.gov"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "friend_add", "kwargs": {"user_id": "dave@device-d.gov"} }');
    """
    if not driver.is_on('service_identity_propagate'):
        return ERROR('service_identity_propagate() is not started')
    from contacts import contactsdb
    from contacts import identitycache
    from main import events
    from userid import global_id
    from userid import id_url
    idurl = strng.to_text(user_id)
    if global_id.IsValidGlobalUser(user_id):
        idurl = global_id.GlobalUserToIDURL(user_id, as_field=False)
    idurl = id_url.field(idurl)
    if not idurl:
        return ERROR('you must specify the global IDURL address where your identity file was last located')

    def _remove():
        if contactsdb.is_correspondent(idurl):
            contactsdb.remove_correspondent(idurl)
            contactsdb.save_correspondents()
            events.send('friend-removed', data=dict(
                idurl=idurl,
                global_id=global_id.idurl2glob(idurl),
            ))
            return OK(message='friend has been removed', api_method='friend_remove')
        return ERROR('friend not found', api_method='friend_remove')

    if id_url.is_cached(idurl):
        return _remove()

    ret = Deferred()
    d = identitycache.immediatelyCaching(idurl)
    d.addErrback(lambda *args: ret.callback(ERROR('failed caching user identity', api_method='friend_remove')))
    d.addCallback(lambda *args: ret.callback(_remove()))
    return ret

#------------------------------------------------------------------------------

def user_ping(user_id, timeout=15, retries=2):
    """
    Sends `Identity` packet to remote peer and wait for an `Ack` packet to check connection status.

    Method can be used to check and verify that remote node is on-line at the moment (if you are also on-line).

    ###### HTTP
        curl -X GET 'localhost:8180/user/ping/v1?user_id=carol@computer-c.net'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "suppliers_ping", "kwargs": {} }');
    """
    if not driver.is_on('service_identity_propagate'):
        return ERROR('service_identity_propagate() is not started')
    from p2p import online_status
    from userid import global_id
    idurl = user_id
    if global_id.IsValidGlobalUser(idurl):
        idurl = global_id.GlobalUserToIDURL(idurl, as_field=False)
    idurl = strng.to_bin(idurl)
    ret = Deferred()
    d = online_status.handshake(
        idurl,
        ack_timeout=int(timeout),
        ping_retries=int(retries),
        channel='api_user_ping',
        keep_alive=False,
    )
    d.addCallback(lambda ok: ret.callback(OK(ok or 'connected', api_method='user_ping')))
    d.addErrback(lambda err: ret.callback(ERROR(err, api_method='user_ping')))
    return ret


def user_status(user_id):
    """
    Returns short info about current on-line status of the given user.

    ###### HTTP
        curl -X GET 'localhost:8180/user/status/v1?user_id=carol@computer-c.net'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "user_status", "kwargs": {"user_id": "carol@computer-c.net"} }');
    """
    if not driver.is_on('service_identity_propagate'):
        return ERROR('service_identity_propagate() is not started')
    from p2p import online_status
    from userid import global_id
    from userid import id_url
    idurl = user_id
    if global_id.IsValidGlobalUser(idurl):
        idurl = global_id.GlobalUserToIDURL(idurl)
    idurl = id_url.field(idurl)
    if not online_status.isKnown(idurl):
        return ERROR('unknown user')
    # state_machine_inst = contact_status.getInstance(idurl)
    # if not state_machine_inst:
    #     return ERROR('error fetching user status')
    return OK({
        'contact_status': online_status.getStatusLabel(idurl),
        'contact_state': online_status.getCurrentState(idurl),
        'idurl': idurl,
        'global_id': global_id.UrlToGlobalID(idurl),
    })


def user_status_check(user_id, timeout=5):
    """
    Returns current online status of a user and only if node is known but disconnected performs "ping" operation.

    ###### HTTP
        curl -X GET 'localhost:8180/user/status/check/v1?user_id=carol@computer-c.net'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "user_status_check", "kwargs": {"user_id": "carol@computer-c.net"} }');
    """
    if not driver.is_on('service_identity_propagate'):
        return ERROR('service_identity_propagate() is not started')
    from p2p import online_status
    from userid import global_id
    from userid import id_url
    idurl = user_id
    if global_id.IsValidGlobalUser(idurl):
        idurl = global_id.GlobalUserToIDURL(idurl)
    idurl = id_url.field(idurl)
    peer_status = online_status.getInstance(idurl)
    if not peer_status:
        return ERROR('peer is not connected')
    ret = Deferred()
    ping_result = Deferred()
    ping_result.addCallback(lambda resp: ret.callback(OK(
        dict(
            idurl=idurl,
            global_id=global_id.UrlToGlobalID(idurl),
            contact_state=peer_status.state,
            contact_status=online_status.stateToLabel(peer_status.state),
        ),
        api_method='user_status_check',
    )))
    if _Debug:
        ping_result.addErrback(lg.errback, debug=_Debug, debug_level=_DebugLevel, method='api.user_status_check')
    ping_result.addErrback(lambda err: ret.errback(err))
    peer_status.automat('ping-now', ping_result, channel=None, ack_timeout=timeout, ping_retries=0)
    return ret


def user_search(nickname, attempts=1):
    """
    Doing lookup of a single `nickname` registered in the DHT network.

    ###### HTTP
        curl -X GET 'localhost:8180/user/search/v1?nickname=carol'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "user_search", "kwargs": {"nickname": "carol"} }');
    """
    from lib import misc
    from userid import global_id
    if not nickname:
        return ERROR('requires nickname of the user')
    if not misc.ValidNickName(nickname):
        return ERROR('invalid nickname')
    if not driver.is_on('service_private_messages'):
        return ERROR('service_private_messages() is not started')

    from chat import nickname_observer
    # nickname_observer.stop_all()
    ret = Deferred()

    def _result(result, nik, pos, idurl):
        return ret.callback(OK({
            'result': result,
            'nickname': nik,
            'position': pos,
            'global_id': global_id.UrlToGlobalID(idurl),
            'idurl': idurl,
        }, api_method='user_search'))

    nickname_observer.find_one(
        nickname,
        attempts=attempts,
        results_callback=_result,
    )
    return ret


def user_observe(nickname, attempts=3):
    """
    Reads all records registered for given `nickname` in the DHT network.

    It could be that multiple users chosen same nickname when creating an identity.

    ###### HTTP
        curl -X GET 'localhost:8180/user/observe/v1?nickname=carol'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "user_observe", "kwargs": {"nickname": "carol"} }');
    """
    from lib import misc
    from userid import global_id
    if not nickname:
        return ERROR('requires nickname of the user')
    if not misc.ValidNickName(nickname):
        return ERROR('invalid nickname')
    if not driver.is_on('service_private_messages'):
        return ERROR('service_private_messages() is not started')

    from chat import nickname_observer
    nickname_observer.stop_all()
    ret = Deferred()
    results = []

    def _result(result, nik, pos, idurl):
        if result != 'finished':
            results.append({
                'result': result,
                'nickname': nik,
                'position': pos,
                'global_id': global_id.UrlToGlobalID(idurl),
                'idurl': idurl,
            })
            return None
        ret.callback(RESULT(results, api_method='user_observe'))
        return None

    reactor.callLater(0.05, nickname_observer.observe_many,  # @UndefinedVariable
        nickname,
        attempts=attempts,
        results_callback=_result,
    )
    return ret

#------------------------------------------------------------------------------

def message_history(recipient_id=None, sender_id=None, message_type=None, offset=0, limit=100):
    """
    Returns chat history stored during communications with given user or messaging group.

    ###### HTTP
        curl -X GET 'localhost:8180/message/history/v1?message_type=group_message&recipient_id=group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "message_history", "kwargs": {"recipient_id" : "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com", "message_type": "group_message"} }');
    """
    if not driver.is_on('service_message_history'):
        return ERROR('service_message_history() is not started')
    from chat import message_database
    from userid import my_id, global_id
    from crypt import my_keys
    if recipient_id is None and sender_id is None:
        return ERROR('recipient_id or sender_id is required')
    if not recipient_id.count('@'):
        from contacts import contactsdb
        recipient_idurl = contactsdb.find_correspondent_by_nickname(recipient_id)
        if not recipient_idurl:
            return ERROR('recipient was not found')
        recipient_id = global_id.UrlToGlobalID(recipient_idurl)
    recipient_glob_id = global_id.ParseGlobalID(recipient_id)
    if not recipient_glob_id['idurl']:
        return ERROR('wrong recipient_id')
    recipient_id = global_id.MakeGlobalID(**recipient_glob_id)
    if not my_keys.is_valid_key_id(recipient_id):
        return ERROR('invalid recipient_id: %s' % recipient_id)
    bidirectional = False
    if message_type in [None, 'private_message', ]:
        bidirectional = True
        if sender_id is None:
            sender_id = my_id.getGlobalID(key_alias='master')
    if _Debug:
        lg.out(_DebugLevel, 'api.message_history with recipient_id=%s sender_id=%s message_type=%s' % (
            recipient_id, sender_id, message_type, ))
    messages = [{'doc': m, } for m in message_database.query(
        sender_id=sender_id,
        recipient_id=recipient_id,
        bidirectional=bidirectional,
        message_types=[message_type, ] if message_type else [],
        offset=offset,
        limit=limit,
    )]
    return RESULT(messages)


def message_send(recipient_id, data, ping_timeout=30, message_ack_timeout=15):
    """
    Sends a text message to remote peer, `recipient_id` is a string with a nickname, global_id or IDURL of the remote user.

    ###### HTTP
        curl -X POST 'localhost:8180/message/send/v1' -d '{"recipient_id": "carlos@computer-c.net", "data": {"message": "Hola Amigo!"}}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "message_send", "kwargs": {"recipient_id": "carlos@computer-c.net", "data": {"message": "Hola Amigos!"}} }');
    """
    if not driver.is_on('service_private_messages'):
        return ERROR('service_private_messages() is not started')
    from stream import message
    from userid import global_id
    from crypt import my_keys
    if not recipient_id.count('@'):
        from contacts import contactsdb
        recipient_idurl = contactsdb.find_correspondent_by_nickname(recipient_id)
        if not recipient_idurl:
            recipient_idurl = strng.to_bin(recipient_id)
        if not recipient_idurl:
            return ERROR('recipient not found')
        recipient_id = global_id.glob2idurl(recipient_idurl, as_field=False)
    glob_id = global_id.ParseGlobalID(recipient_id)
    if not glob_id['idurl']:
        return ERROR('wrong recipient')
    target_glob_id = global_id.MakeGlobalID(**glob_id)
    if not my_keys.is_valid_key_id(target_glob_id):
        return ERROR('invalid key_id: %s' % target_glob_id)
#     if not my_keys.is_key_registered(target_glob_id):
#         return ERROR('unknown key_id: %s' % target_glob_id)
    if _Debug:
        lg.out(_DebugLevel, 'api.message_send to "%s" ping_timeout=%d message_ack_timeout=%d' % (
            target_glob_id, ping_timeout, message_ack_timeout, ))
    result = message.send_message(
        json_data=data,
        recipient_global_id=target_glob_id,
        ping_timeout=ping_timeout,
        message_ack_timeout=message_ack_timeout,
    )
    ret = Deferred()
    result.addCallback(lambda packet: ret.callback(OK(strng.to_text(packet), api_method='message_send')))
    result.addErrback(lambda err: ret.callback(ERROR(err, api_method='message_send')))
    return ret


def message_send_group(group_key_id, data):
    """
    Sends a text message to a group of users.

    ###### HTTP
        curl -X POST 'localhost:8180/message/send/group/v1' -d '{"group_key_id": "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com", "data": {"message": "Hola Amigos!"}}' 

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "message_send_group", "kwargs": {"group_key_id": "group_95d0fedc46308e2254477fcb96364af9$alice@server-a.com", "data": {"message": "Hola Amigos!"}} }');
    """
    if not driver.is_on('service_private_groups'):
        return ERROR('service_private_groups() is not started')
    from userid import global_id
    from crypt import my_keys
    from access import group_member
    if not group_key_id.startswith('group_'):
        return ERROR('invalid group id')
    glob_id = global_id.ParseGlobalID(group_key_id)
    if not glob_id['idurl']:
        return ERROR('wrong group id')
    if not my_keys.is_key_registered(group_key_id):
        return ERROR('unknown group key')
    this_group_member = group_member.get_active_group_member(group_key_id)
    if not this_group_member:
        return ERROR('group is not active')
    if this_group_member.state not in ['IN_SYNC!', 'QUEUE?', ]:
        return ERROR('group is not synchronized yet')
    if _Debug:
        lg.out(_DebugLevel, 'api.message_send_group to %r' % group_key_id)
    this_group_member.automat('push-message', json_payload=data)
    return OK()


def message_receive(consumer_callback_id, direction='incoming', message_types='private_message,group_message', polling_timeout=60):
    """
    This method can be used by clients to listen and process streaming messages.

    If there are no pending messages received yet in the stream, this method will block and will be waiting for any message to come.

    If some messages are already waiting in the stream to be consumed method will return them immediately.
    As soon as client received and processed the response messages are marked as "consumed" and released from the stream.

    Client should call that method again to listen for next messages in the stream. You can use `polling_timeout` parameter
    to control blocking for receiving duration. This is very similar to a long polling technique.

    Once client stopped calling that method and do not "consume" messages anymor given `consumer_callback_id` will be dropped
    after 100 non-collected messages.

    You can set parameter `direction=outgoing` to only populate messages you are sending to others - can be useful for UI clients.

    Also you can use parameter `message_types` to select only specific types of messages: "private_message" or "group_message".

    This method is only make sense for HTTP interface, because using a WebSocket client will receive streamed message directly.

    ###### HTTP
        curl -X GET 'localhost:8180/message/receive/my-client-group-messages/v1?message_types=group_message'
    """
    if not driver.is_on('service_private_messages'):
        return ERROR('service_private_messages() is not started')
    from stream import message
    from p2p import p2p_service
    ret = Deferred()
    if strng.is_text(message_types):
        message_types = message_types.split(',')

    def _on_pending_messages(pending_messages):
        result = []
        packets_to_ack = {}
        for msg in pending_messages:
            try:
                result.append({
                    'data': msg['data'],
                    'recipient': msg['to'],
                    'sender': msg['from'],
                    'time': msg['time'],
                    'message_id': msg['packet_id'],
                    'dir': msg['dir'],
                })
            except:
                lg.exc()
                continue
            if msg['owner_idurl']:
                packets_to_ack[msg['packet_id']] = msg['owner_idurl']
        for packet_id, owner_idurl in packets_to_ack.items():
            p2p_service.SendAckNoRequest(owner_idurl, packet_id)
        packets_to_ack.clear()
        if _Debug:
            lg.out(_DebugLevel, 'api.message_receive._on_pending_messages returning : %r' % result)
        ret.callback(RESULT(result, api_method='message_receive'))
        return len(result) > 0

    def _on_consume_error(err):
        if _Debug:
            lg.args(_DebugLevel, err=err)
        if isinstance(err, list) and len(err) > 0:
            err = err[0]
        if isinstance(err, Failure):
            try:
                err = err.getErrorMessage()
            except:
                err = strng.to_text(err)
        if err.lower().count('cancelled'):
            ret.callback(RESULT([], api_method='message_receive'))
            return None
        if not str(err):
            ret.callback(RESULT([], api_method='message_receive'))
            return None
        ret.callback(ERROR(err))
        return None

    d = message.consume_messages(
        consumer_callback_id=consumer_callback_id,
        direction=direction,
        message_types=message_types,
        reset_callback=True,
    )
    d.addCallback(_on_pending_messages)
    d.addErrback(_on_consume_error)
    if polling_timeout is not None:
        d.addTimeout(polling_timeout, clock=reactor)
    if _Debug:
        lg.out(_DebugLevel, 'api.message_receive "%s" started' % consumer_callback_id)
    return ret

#------------------------------------------------------------------------------

def suppliers_list(customer_id=None, verbose=False):
    """
    This method returns a list of your suppliers.
    Those nodes stores your encrypted file or file uploaded by other users that still belongs to you.

    Your BitDust node also sometimes need to connect to suppliers of other users to upload or download shared data.
    Those external suppliers lists are cached and can be selected here with `customer_id` optional parameter.

    ###### HTTP
        curl -X GET 'localhost:8180/supplier/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "suppliers_list", "kwargs": {} }');
    """
    if not driver.is_on('service_customer'):
        return ERROR('service_customer() is not started')
    from contacts import contactsdb
    from customer import supplier_connector
    from p2p import online_status
    from lib import misc
    from userid import my_id
    from userid import id_url
    from userid import global_id
    from storage import backup_matrix
    customer_idurl = strng.to_bin(customer_id)
    if not customer_idurl:
        customer_idurl = my_id.getLocalID().to_bin()
    else:
        if global_id.IsValidGlobalUser(customer_id):
            customer_idurl = global_id.GlobalUserToIDURL(customer_id, as_field=False)
    customer_idurl = id_url.field(customer_idurl)
    results = []
    for (pos, supplier_idurl, ) in enumerate(contactsdb.suppliers(customer_idurl)):
        if not supplier_idurl:
            r = {
                'position': pos,
                'idurl': '',
                'global_id': '',
                'supplier_state': None,
                'connected': None,
                'contact_status': 'offline',
                'contact_state': 'OFFLINE',
            }
            results.append(r)
            continue
        r = {
            'position': pos,
            'idurl': supplier_idurl,
            'global_id': global_id.UrlToGlobalID(supplier_idurl),
            'supplier_state':
                None if not supplier_connector.is_supplier(supplier_idurl, customer_idurl)
                else supplier_connector.by_idurl(supplier_idurl, customer_idurl).state,
            'connected': misc.readSupplierData(supplier_idurl, 'connected', customer_idurl),
            'contact_status': 'offline',
            'contact_state': 'OFFLINE',
        }
        if online_status.isKnown(supplier_idurl):
            r['contact_status'] = online_status.getStatusLabel(supplier_idurl)
            r['contact_state'] = online_status.getCurrentState(supplier_idurl)
        # if contact_status.isKnown(supplier_idurl):
        #     cur_state = contact_status.getInstance(supplier_idurl).state
        #     r['contact_status'] = contact_status.stateToLabel(cur_state)
        #     r['contact_state'] = cur_state
        if verbose:
            _files, _total, _report = backup_matrix.GetSupplierStats(pos, customer_idurl=customer_idurl)
            r['listfiles'] = misc.readSupplierData(supplier_idurl, 'listfiles', customer_idurl)
            r['fragments'] = {
                'items': _files,
                'files': _total,
                'details': _report,
            }
        results.append(r)
    return RESULT(results)


def supplier_change(position=None, supplier_id=None, new_supplier_id=None):
    """
    The method will execute a fire/hire process for given supplier. You can specify which supplier to be replaced by position or ID.

    If optional parameter `new_supplier_id` was not specified another random node will be found via DHT network and it will
    replace the current supplier. Otherwise `new_supplier_id` must be an existing node in the network and
    the process will try to connect and use that node as a new supplier.

    As soon as new node is found and connected, rebuilding of all uploaded data will be automatically started and new supplier
    will start getting reconstructed fragments of your data piece by piece.

    ###### HTTP
        curl -X POST 'localhost:8180/supplier/change/v1' -d '{"position": 1, "new_supplier_id": "carol@computer-c.net"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "supplier_change", "kwargs": {"position": 1, "new_supplier_id": "carol@computer-c.net"} }');
    """
    if not driver.is_on('service_employer'):
        return ERROR('service_employer() is not started')
    from contacts import contactsdb
    from userid import my_id
    from userid import global_id
    customer_idurl = my_id.getLocalID()
    supplier_idurl = None
    if position is not None:
        supplier_idurl = contactsdb.supplier(int(position), customer_idurl=customer_idurl)
    else:
        if global_id.IsValidGlobalUser(supplier_id):
            supplier_idurl = global_id.GlobalUserToIDURL(supplier_id)
    supplier_idurl = strng.to_bin(supplier_idurl)
    if not supplier_idurl or not contactsdb.is_supplier(supplier_idurl, customer_idurl=customer_idurl):
        return ERROR('supplier not found')
    new_supplier_idurl = new_supplier_id
    if new_supplier_id is not None:
        if global_id.IsValidGlobalUser(new_supplier_id):
            new_supplier_idurl = global_id.GlobalUserToIDURL(new_supplier_id, as_field=False)
        new_supplier_idurl = strng.to_bin(new_supplier_idurl)

        if contactsdb.is_supplier(new_supplier_idurl, customer_idurl=customer_idurl):
            return ERROR('peer %r is your supplier already' % new_supplier_idurl)
    ret = Deferred()

    def _do_change(x):
        from customer import fire_hire
        from customer import supplier_finder
        if new_supplier_idurl is not None:
            supplier_finder.InsertSupplierToHire(new_supplier_idurl)
        fire_hire.AddSupplierToFire(supplier_idurl)
        fire_hire.A('restart')
        if new_supplier_idurl is not None:
            ret.callback(OK('supplier "%s" will be replaced by "%s"' % (supplier_idurl, new_supplier_idurl), api_method='supplier_change'))
        else:
            ret.callback(OK('supplier "%s" will be replaced by a new random peer' % supplier_idurl, api_method='supplier_change'))
        return None

    if new_supplier_id is None:
        _do_change(None)
        return ret
    from p2p import online_status
    d = online_status.handshake(
        idurl=new_supplier_idurl,
        channel='supplier_change',
        keep_alive=True,
    )
    d.addCallback(_do_change)
    d.addErrback(lambda err: ret.callback(ERROR(err)))
    return ret


def suppliers_ping():
    """
    Sends short requests to all suppliers to verify current connection status.

    ###### HTTP
        curl -X POST 'localhost:8180/supplier/ping/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "suppliers_ping", "kwargs": {} }');
    """
    if not driver.is_on('service_customer'):
        return ERROR('service_customer() is not started')
    from p2p import propagate
    propagate.SlowSendSuppliers(0.1)
    return OK('sent requests to all suppliers')


def suppliers_dht_lookup(customer_id=None):
    """
    Scans DHT network for key-value pairs related to given customer and returns a list its suppliers.

    ###### HTTP
        curl -X GET 'localhost:8180/supplier/list/dht/v1?customer_id=alice@server-a.com'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "suppliers_dht_lookup", "kwargs": {"customer_id": "alice@server-a.com"} }');
    """
    if not driver.is_on('service_entangled_dht'):
        return ERROR('service_entangled_dht() is not started')
    from dht import dht_relations
    from userid import my_id
    from userid import id_url
    from userid import global_id
    customer_idurl = None
    if not customer_id:
        customer_idurl = my_id.getLocalID().to_bin()
    else:
        customer_idurl = strng.to_bin(customer_id)
        if global_id.IsValidGlobalUser(customer_id):
            customer_idurl = global_id.GlobalUserToIDURL(customer_id, as_field=False)
    customer_idurl = id_url.field(customer_idurl)
    ret = Deferred()
    d = dht_relations.read_customer_suppliers(customer_idurl, as_fields=False, use_cache=False)
    d.addCallback(lambda result: ret.callback(RESULT(result, api_method='suppliers_dht_lookup')))
    d.addErrback(lambda err: ret.callback(ERROR(err)))
    return ret

#------------------------------------------------------------------------------


def customers_list(verbose=False):
    """
    Method returns list of your customers - nodes for whom you are storing data on that host.

    ###### HTTP
        curl -X GET 'localhost:8180/customer/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "customers_list", "kwargs": {} }');
    """
    if not driver.is_on('service_supplier'):
        return ERROR('service_supplier() is not started')
    from contacts import contactsdb
    from p2p import online_status
    from userid import global_id
    results = []
    for pos, customer_idurl in enumerate(contactsdb.customers()):
        if not customer_idurl:
            r = {
                'position': pos,
                'global_id': '',
                'idurl': '',
                'contact_status': 'offline',
                'contact_state': 'OFFLINE',
            }
            results.append(r)
            continue
        r = {
            'position': pos,
            'global_id': global_id.UrlToGlobalID(customer_idurl),
            'idurl': customer_idurl,
            'contact_status': 'offline',
            'contact_state': 'OFFLINE',
        }
        if online_status.isKnown(customer_idurl):
            r['contact_status'] = online_status.getStatusLabel(customer_idurl)
            r['contact_state'] = online_status.getCurrentState(customer_idurl)
        # if contact_status.isKnown(customer_idurl):
        #     cur_state = contact_status.getInstance(customer_idurl).state
        #     r['contact_status'] = contact_status.stateToLabel(cur_state)
        #     r['contact_state'] = cur_state
        results.append(r)
    return RESULT(results)


def customer_reject(customer_id):
    """
    Stop supporting given customer, remove all related files from local disc, close connections with that node.

    ###### HTTP
        curl -X DELETE 'localhost:8180/customer/reject/v1' -d '{"customer_id": "dave@device-d.gov"}'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "customer_reject", "kwargs": {"customer_id": "dave@device-d.gov"} }');
    """
    if not driver.is_on('service_supplier'):
        return ERROR('service_supplier() is not started')
    from contacts import contactsdb
    from storage import accounting
    from main import settings
    from main import events
    from supplier import local_tester
    from raid import eccmap
    from p2p import p2p_service
    from lib import packetid
    from userid import global_id
    from userid import id_url
    customer_idurl = customer_id
    if global_id.IsValidGlobalUser(customer_id):
        customer_idurl = global_id.GlobalUserToIDURL(customer_id)
    customer_idurl = id_url.field(customer_idurl)
    if not contactsdb.is_customer(customer_idurl):
        return ERROR('customer not found')
    # send packet to notify about service from us was rejected
    # TODO: - this is not yet handled on other side
    p2p_service.SendFailNoRequest(customer_idurl, packetid.UniqueID(), 'service rejected')
    # remove from customers list
    current_customers = contactsdb.customers()
    current_customers.remove(customer_idurl)
    contactsdb.remove_customer_meta_info(customer_idurl)
    # remove records for this customers from quotas info
    space_dict, _ = accounting.read_customers_quotas()
    consumed_by_cutomer = space_dict.pop(customer_idurl, 0)
    consumed_space = accounting.count_consumed_space(space_dict)
    new_free_space = settings.getDonatedBytes() - int(consumed_space)
    accounting.write_customers_quotas(space_dict, new_free_space)
    contactsdb.update_customers(current_customers)
    contactsdb.save_customers()
    events.send('existing-customer-terminated', dict(
        idurl=customer_idurl,
        ecc_map=eccmap.Current().name,
    ))
    # restart local tester
    local_tester.TestUpdateCustomers()
    return OK('customer "%s" rejected, "%s" bytes were freed' % (customer_idurl, consumed_by_cutomer))


def customers_ping():
    """
    Check current on-line status of all customers.

    ###### HTTP
        curl -X POST 'localhost:8180/customer/ping/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "customers_ping", "kwargs": {} }');
    """
    if not driver.is_on('service_supplier'):
        return ERROR('service_supplier() is not started')
    from p2p import propagate
    propagate.SlowSendCustomers(0.1)
    return OK('sent requests to all customers')

#------------------------------------------------------------------------------

def space_donated():
    """
    Returns detailed info about quotas and usage of the storage space you donated to your customers.

    ###### HTTP
        curl -X GET 'localhost:8180/space/donated/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "space_donated", "kwargs": {} }');
    """
    from storage import accounting
    result = accounting.report_donated_storage()
    if _Debug:
        lg.out(_DebugLevel, 'api.space_donated finished with %d customers and %d errors' % (
        len(result['customers']), len(result['errors']),))
    for err in result['errors']:
        if _Debug:
            lg.out(_DebugLevel, '    %s' % err)
    errors = result.pop('errors', [])
    return OK(result, errors=errors,)


def space_consumed():
    """
    Returns info about current usage of the storage space provided by your suppliers.

    ###### HTTP
        curl -X GET 'localhost:8180/space/consumed/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "space_consumed", "kwargs": {} }');
    """
    from storage import accounting
    result = accounting.report_consumed_storage()
    if _Debug:
        lg.out(_DebugLevel, 'api.space_consumed finished')
    return OK(result)


def space_local():
    """
    Returns info about current usage of your local disk drive.

    ###### HTTP
        curl -X GET 'localhost:8180/space/local/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "space_local", "kwargs": {} }');
    """
    from storage import accounting
    result = accounting.report_local_storage()
    if _Debug:
        lg.out(_DebugLevel, 'api.space_local finished')
    return OK(result)

#------------------------------------------------------------------------------

def services_list(with_configs=False):
    """
    Returns detailed info about all currently running network services.

    Pass `with_configs=True` to also see current program settings values related to each service.

    This is a very useful method when you need to investigate a problem in the software.

    ###### HTTP
        curl -X GET 'localhost:8180/service/list/v1?with_configs=1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "services_list", "kwargs": {"with_configs": 1} }');
    """
    result = []
    for name, svc in sorted(list(driver.services().items()), key=lambda i: i[0]):
        svc_info = {
            'index': svc.index,
            'name': name,
            'state': svc.state,
            'enabled': svc.enabled(),
            'installed': svc.installed(),
            'depends': svc.dependent_on()
        }
        if with_configs:
            svc_configs = []
            for child in config.conf().listEntries(svc.config_path.replace('/enabled', '')):
                svc_configs.append(config.conf().toJson(child))
            svc_info['configs'] = svc_configs
        result.append(svc_info)
    if _Debug:
        lg.out(_DebugLevel, 'api.services_list responded with %d items' % len(result))
    return RESULT(result)


def service_info(service_name):
    """
    Returns detailed info about single service.

    ###### HTTP
        curl -X GET 'localhost:8180/service/info/service_private_groups/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "service_info", "kwargs": {"service_name": "service_private_groups"} }');
    """
    svc = driver.services().get(service_name, None)
    if svc is None:
        service_name = 'service_' + service_name.replace('-', '_')
        svc = driver.services().get(service_name, None)
    if svc is None:
        return ERROR('service "%s" not found' % service_name)
    return OK({
        'index': svc.index,
        'name': svc.service_name,
        'state': svc.state,
        'enabled': svc.enabled(),
        'installed': svc.installed(),
        'config_path': svc.config_path,
        'depends': svc.dependent_on()
    })


def service_start(service_name):
    """
    Starts given service immediately.

    This method also set `True` for correspondent option in the program settings to mark the service as enabled:

        .bitdust/config/services/[service name]/enabled

    Other dependent services, if they were enabled before but stopped, also will be started.

    ###### HTTP
        curl -X POST 'localhost:8180/service/start/service_supplier/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "service_start", "kwargs": {"service_name": "service_supplier"} }');
    """
    if _Debug:
        lg.out(_DebugLevel, 'api.service_start : %s' % service_name)
    svc = driver.services().get(service_name, None)
    if svc is None:
        service_name = 'service_' + service_name.replace('-', '_')
        svc = driver.services().get(service_name, None)
    if svc is None:
        lg.warn('service "%s" not found' % service_name)
        return ERROR('service "%s" was not found' % service_name)
    if svc.state == 'ON':
        lg.warn('service "%s" already started' % service_name)
        return ERROR('service "%s" already started' % service_name)
    current_config = config.conf().getBool(svc.config_path)
    if current_config:
        lg.warn('service "%s" already enabled' % service_name)
        return ERROR('service "%s" already enabled' % service_name)
    config.conf().setBool(svc.config_path, True)
    return OK('"%s" was switched on' % service_name)


def service_stop(service_name):
    """
    Stop given service immediately.

    This method also set `False` for correspondent option in the program settings to mark the service as disabled:

        .bitdust/config/services/[service name]/enabled

    Dependent services will be stopped as well but will not be disabled.

    ###### HTTP
        curl -X POST 'localhost:8180/service/stop/service_supplier/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "service_stop", "kwargs": {"service_name": "service_supplier"} }');
    """
    if _Debug:
        lg.out(_DebugLevel, 'api.service_stop : %s' % service_name)
    svc = driver.services().get(service_name, None)
    if svc is None:
        service_name = 'service_' + service_name.replace('-', '_')
        svc = driver.services().get(service_name, None)
    if svc is None:
        lg.warn('service "%s" not found' % service_name)
        return ERROR('service "%s" not found' % service_name)
    current_config = config.conf().getBool(svc.config_path)
    if current_config is None:
        lg.warn('config item "%s" was not found' % svc.config_path)
        return ERROR('config item "%s" was not found' % svc.config_path)
    if current_config is False:
        lg.warn('service "%s" already disabled' % service_name)
        return ERROR('service "%s" already disabled' % service_name)
    config.conf().setBool(svc.config_path, False)
    return OK('"%s" was switched off' % service_name)


def service_restart(service_name, wait_timeout=10):
    """
    This method will stop given service and start it again, but only if it is already enabled.
    It will not modify corresponding option for that service in the program settings.

    All dependent services will be restarted as well.

    Very useful method when you need to reload some parts of the application without full process restart.

    ###### HTTP
        curl -X POST 'localhost:8180/service/restart/service_customer/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "service_restart", "kwargs": {"service_name": "service_customer"} }');
    """
    svc = driver.services().get(service_name, None)
    if _Debug:
        lg.out(_DebugLevel, 'api.service_restart : %s' % service_name)
    if svc is None:
        service_name = 'service_' + service_name.replace('-', '_')
        svc = driver.services().get(service_name, None)
    if svc is None:
        lg.warn('service "%s" not found' % service_name)
        return ERROR('service "%s" not found' % service_name)
    ret = Deferred()
    d = driver.restart(service_name, wait_timeout=wait_timeout)
    d.addCallback(lambda resp: ret.callback(OK(resp, api_method='service_restart')))
    d.addErrback(lambda err: ret.callback(ERROR(err, api_method='service_restart')))
    return ret

#------------------------------------------------------------------------------

def packets_list():
    """
    Returns list of incoming and outgoing signed packets running at the moment.

    ###### HTTP
        curl -X GET 'localhost:8180/packet/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "packets_list", "kwargs": {} }');
    """
    if not driver.is_on('service_gateway'):
        return ERROR('service_gateway() is not started')
    from transport import packet_in
    from transport import packet_out
    result = []
    for pkt_out in packet_out.queue():
        items = []
        for itm in pkt_out.items:
            items.append({
                'transfer_id': itm.transfer_id,
                'proto': itm.proto,
                'host': itm.host,
                'size': itm.size,
                'bytes_sent': itm.bytes_sent,
            })
        result.append({
            'direction': 'outgoing',
            'command': pkt_out.outpacket.Command,
            'packet_id': pkt_out.outpacket.PacketID,
            'label': pkt_out.label,
            'target': pkt_out.remote_idurl,
            'description': pkt_out.description,
            'label': pkt_out.label,
            'response_timeout': pkt_out.response_timeout,
            'items': items,
        })
    for pkt_in in list(packet_in.inbox_items().values()):
        result.append({
            'direction': 'incoming',
            'transfer_id': pkt_in.transfer_id,
            'label': pkt_in.label,
            'target': pkt_in.sender_idurl,
            'label': pkt_in.label,
            'timeout': pkt_in.timeout,
            'proto': pkt_in.proto,
            'host': pkt_in.host,
            'size': pkt_in.size,
            'bytes_received': pkt_in.bytes_received,
        })
    return RESULT(result)


def packets_stats():
    """
    Returns detailed info about overall network usage.

    ###### HTTP
        curl -X GET 'localhost:8180/packet/stats/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "packets_stats", "kwargs": {} }');
    """
    if not driver.is_on('service_gateway'):
        return ERROR('service_gateway() is not started')
    from p2p import p2p_stats
    return OK({
        'in': p2p_stats.counters_in(),
        'out': p2p_stats.counters_out(),
    })

#------------------------------------------------------------------------------

def transfers_list():
    """
    Returns list of current data fragments transfers to/from suppliers.

    ###### HTTP
        curl -X GET 'localhost:8180/transfer/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "transfers_list", "kwargs": {} }');
    """
    if not driver.is_on('service_data_motion'):
        return ERROR('service_data_motion() is not started')
    from stream import io_throttle
    from userid import global_id
    result = []
    for supplier_idurl in io_throttle.throttle().ListSupplierQueues():
        r = {
            'idurl': supplier_idurl,
            'global_id': global_id.UrlToGlobalID(supplier_idurl),
            'outgoing': [],
            'incoming': [],
        }
        q = io_throttle.throttle().GetSupplierQueue(supplier_idurl)
        for packet_id in q.ListSendItems():
            i = q.GetSendItem(packet_id)
            if i:
                r['outgoing'].append({
                    'packet_id': i.packetID,
                    'owner_id': i.ownerID,
                    'remote_id': i.remoteID,
                    'customer': i.customerID,
                    'remote_path': i.remotePath,
                    'filename': i.fileName,
                    'created': i.created,
                    'sent': i.sendTime,
                })
        for packet_id in q.ListRequestItems():
            i = q.GetRequestItem(packet_id)
            if i:
                r['incoming'].append({
                    'packet_id': i.packetID,
                    'owner_id': i.ownerID,
                    'remote_id': i.remoteID,
                    'customer': i.customerID,
                    'remote_path': i.remotePath,
                    'filename': i.fileName,
                    'created': i.created,
                    'requested': i.requestTime,
                })
        result.append(r)
    return RESULT(result)


def connections_list(protocols=None):
    """
    Returns list of opened/active network connections.

    Argument `protocols` can be used to select which protocols to be present in the response:

    ###### HTTP
        curl -X GET 'localhost:8180/connection/list/v1?protocols=tcp,udp,proxy'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "connections_list", "kwargs": {"protocols": ["tcp", "udp", "proxy"]} }');
    """
    if not driver.is_on('service_gateway'):
        return ERROR('service_gateway() is not started')
    from transport import gateway
    from userid import global_id
    result = []
    if not protocols:
        protocols = gateway.list_active_transports()
    for proto in protocols:
        if not gateway.is_ready():
            continue
        if not gateway.is_installed(proto):
            continue
        for connection in gateway.list_active_sessions(proto):
            item = {
                'status': 'unknown',
                'state': 'unknown',
                'proto': proto,
                'host': 'unknown',
                'global_id': 'unknown',
                'idurl': 'unknown',
                'bytes_sent': 0,
                'bytes_received': 0,
            }
            if proto == 'tcp':
                if hasattr(connection, 'stream'):
                    try:
                        host = '%s:%s' % (connection.peer_address[0], connection.peer_address[1])
                    except:
                        host = 'unknown'
                    item.update({
                        'status': 'active',
                        'state': connection.state,
                        'host': host,
                        'global_id': global_id.UrlToGlobalID(connection.peer_idurl or ''),
                        'idurl': connection.peer_idurl or '',
                        'bytes_sent': connection.total_bytes_sent or 0,
                        'bytes_received': connection.total_bytes_received or 0,
                    })
                else:
                    try:
                        host = '%s:%s' % (connection.connection_address[0], connection.connection_address[1])
                    except:
                        host = 'unknown'
                    item.update({
                        'status': 'connecting',
                        'host': host,
                    })
            elif proto == 'udp':
                try:
                    host = '%s:%s' % (connection.peer_address[0], connection.peer_address[1])
                except:
                    host = 'unknown'
                item.update({
                    'status': 'active',
                    'state': connection.state,
                    'host': host,
                    'global_id': global_id.UrlToGlobalID(connection.peer_idurl or ''),
                    'idurl': connection.peer_idurl or '',
                    'bytes_sent': connection.bytes_sent or 0,
                    'bytes_received': connection.bytes_received or 0,
                })
            elif proto == 'proxy':
                info = connection.to_json()
                item.update({
                    'status': 'active',
                    'state': info['state'],
                    'host': info['host'] or '',
                    'global_id': global_id.UrlToGlobalID(info['idurl'] or ''),
                    'idurl': info['idurl'] or '',
                    'bytes_sent': info['bytes_sent'] or 0,
                    'bytes_received': info['bytes_received'] or 0,
                })
            else:
                lg.warn('unknown proto %r: %r' % (proto, connection, ))
            result.append(item)
    return RESULT(result)


def streams_list(protocols=None):
    """
    Returns list of running streams of data fragments with recent upload/download progress percentage.

    ###### HTTP
        curl -X GET 'localhost:8180/stream/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "streams_list", "kwargs": {} }');
    """
    if not driver.is_on('service_gateway'):
        return ERROR('service_gateway() is not started')
    from transport import gateway
    from lib import misc
    result = []
    if not protocols:
        protocols = gateway.list_active_transports()
    for proto in protocols:
        if not gateway.is_ready():
            continue
        if not gateway.is_installed(proto):
            continue
        for stream in gateway.list_active_streams(proto):
            item = {
                'proto': proto,
                'stream_id': '',
                'type': '',
                'bytes_current': -1,
                'bytes_total': -1,
                'progress': '0%',
            }
            if proto == 'tcp':
                if hasattr(stream, 'bytes_received'):
                    item.update({
                        'stream_id': stream.file_id,
                        'type': 'in',
                        'bytes_current': stream.bytes_received,
                        'bytes_total': stream.size,
                        'progress': misc.value2percent(stream.bytes_received, stream.size, 0)
                    })
                elif hasattr(stream, 'bytes_sent'):
                    item.update({
                        'stream_id': stream.file_id,
                        'type': 'out',
                        'bytes_current': stream.bytes_sent,
                        'bytes_total': stream.size,
                        'progress': misc.value2percent(stream.bytes_sent, stream.size, 0)
                    })
            elif proto == 'udp':
                if hasattr(stream.consumer, 'bytes_received'):
                    item.update({
                        'stream_id': stream.stream_id,
                        'type': 'in',
                        'bytes_current': stream.consumer.bytes_received,
                        'bytes_total': stream.consumer.size,
                        'progress': misc.value2percent(stream.consumer.bytes_received, stream.consumer.size, 0)
                    })
                elif hasattr(stream.consumer, 'bytes_sent'):
                    item.update({
                        'stream_id': stream.stream_id,
                        'type': 'out',
                        'bytes_current': stream.consumer.bytes_sent,
                        'bytes_total': stream.consumer.size,
                        'progress': misc.value2percent(stream.consumer.bytes_sent, stream.consumer.size, 0)
                    })
            elif proto == 'proxy':
                pass
            result.append(item)
    return RESULT(result)

#------------------------------------------------------------------------------

def queues_list():
    """
    Returns list of registered streaming queues.

    ###### HTTP
        curl -X GET 'localhost:8180/queue/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "queues_list", "kwargs": {} }');
    """
    if not driver.is_on('service_p2p_notifications'):
        return ERROR('service_p2p_notifications() is not started')
    from stream import p2p_queue
    return RESULT([{
        'queue_id': queue_id,
        'messages': len(p2p_queue.queue(queue_id)),
    } for queue_id in p2p_queue.queue().keys()])


def queue_consumers_list():
    """
    Returns list of registered queue consumers.

    ###### HTTP
        curl -X GET 'localhost:8180/queue/consumer/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "queue_consumers_list", "kwargs": {} }');
    """
    if not driver.is_on('service_p2p_notifications'):
        return ERROR('service_p2p_notifications() is not started')
    from stream import p2p_queue
    return RESULT([{
        'consumer_id': consumer_info.consumer_id,
        'queues': consumer_info.queues,
        'state': consumer_info.state,
        'consumed': consumer_info.consumed_messages,
    } for consumer_info in p2p_queue.consumer().values()])


def queue_producers_list():
    """
    Returns list of registered queue producers.

    ###### HTTP
        curl -X GET 'localhost:8180/queue/producer/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "queue_producers_list", "kwargs": {} }');
    """
    if not driver.is_on('service_p2p_notifications'):
        return ERROR('service_p2p_notifications() is not started')
    from stream import p2p_queue
    return RESULT([{
        'producer_id': producer_info.producer_id,
        'queues': producer_info.queues,
        'state': producer_info.state,
        'produced': producer_info.produced_messages,
    } for producer_info in p2p_queue.producer().values()])

#------------------------------------------------------------------------------

def nickname_get():
    """
    """
    from main import settings
    if not driver.is_on('service_private_messages'):
        return ERROR('service_private_messages() is not started')
    return OK({'nickname': settings.getNickName(), })


def nickname_set(nickname):
    """
    Starts nickname_holder() machine to register and keep your nickname in DHT
    network.
    """
    from lib import misc
    if not nickname:
        return ERROR('requires nickname of the user')
    if not misc.ValidNickName(nickname):
        return ERROR('invalid nickname')
    if not driver.is_on('service_private_messages'):
        return ERROR('service_private_messages() is not started')
    from chat import nickname_holder
    from main import settings
    from userid import my_id
    settings.setNickName(nickname)
    ret = Deferred()

    def _nickname_holder_result(result, key):
        nickname_holder.A().remove_result_callback(_nickname_holder_result)
        return ret.callback(OK(
            {
                'success': result,
                'nickname': key,
                'global_id': my_id.getGlobalID(),
                'idurl': my_id.getLocalID(),
            },
            api_method='nickname_set',
        ))

    nickname_holder.A().add_result_callback(_nickname_holder_result)
    nickname_holder.A('set', nickname)
    return ret

#------------------------------------------------------------------------------

def broadcast_send_message(payload):
    """
    Sends broadcast message to all peers in the network.

    Message must be provided in `payload` argument is a Json object.

    WARNING! Please, do not send too often and do not send more then
    several kilobytes per message.
    """
    if not driver.is_on('service_broadcasting'):
        return ERROR('service_broadcasting() is not started')
    from broadcast import broadcast_service
    from broadcast import broadcast_listener
    from broadcast import broadcaster_node
    msg = broadcast_service.send_broadcast_message(payload)
    current_states = dict()
    if broadcaster_node.A():
        current_states[broadcaster_node.A().name] = broadcaster_node.A().state
    if broadcast_listener.A():
        current_states[broadcast_listener.A().name] = broadcast_listener.A().state
    if _Debug:
        lg.out(_DebugLevel, 'api.broadcast_send_message : %s, %s' % (msg, current_states))
    return RESULT([msg, current_states, ])

#------------------------------------------------------------------------------

def event_send(event_id, json_data=None):
    from main import events
    json_payload = None
    json_length = 0
    if json_data and strng.is_string(json_data):
        json_length = len(json_data)
        try:
            json_payload = jsn.loads(strng.to_text(json_data or '{}'))
        except:
            return ERROR('json data payload is not correct')
    evt = events.send(event_id, data=json_payload)
    if _Debug:
        lg.out(_DebugLevel, 'api.event_send "%s" was fired to local node with %d bytes payload' % (event_id, json_length, ))
    return OK({'event_id': event_id, 'created': evt.created, })


def event_listen(consumer_id):
    from main import events
    ret = Deferred()

    def _on_pending_events(pending_events):
        result = []
        for evt in pending_events:
            if evt['type'] != 'event':
                continue
            result.append({
                'id': evt['id'],
                'data': evt['data'],
                'time': evt['time'],
            })
        ret.callback(OK(result, api_method='event_listen'))
        return len(result) > 0

    d = events.consume_events(consumer_id)
    d.addCallback(_on_pending_events)
    d.addErrback(lambda err: ret.callback(ERROR(err, api_method='event_listen')))
    return ret

#------------------------------------------------------------------------------

def network_stun(udp_port=None, dht_port=None):
    """
    """
    from stun import stun_client
    ret = Deferred()
    d = stun_client.safe_stun(udp_port=udp_port, dht_port=dht_port)
    d.addBoth(lambda r: ret.callback(OK(r, api_method='network_stun')))
    return ret


def network_reconnect():
    """
    Sends "reconnect" event to network_connector() Automat in order to refresh
    network connection.

    Return:

        {'status': 'OK', 'result': 'reconnected'}
    """
    if not driver.is_on('service_network'):
        return ERROR('service_network() is not started')
    from p2p import network_connector
    if _Debug:
        lg.out(_DebugLevel, 'api.network_reconnect')
    network_connector.A('reconnect')
    return OK('reconnected')


def network_connected(wait_timeout=5):
    """
    Be sure BitDust software is connected to other nodes in the network.
    If all is good this method will block for `wait_timeout` seconds.
    In case of some network issues method will return result asap.
    """
    if _Debug:
        lg.out(_DebugLevel + 10, 'api.network_connected  wait_timeout=%r' % wait_timeout)
    if not driver.is_on('service_network'):
        return ERROR('service_network() is not started')
    from userid import my_id
    from automats import automat
    ret = Deferred()

    if driver.is_enabled('service_proxy_transport'):
        p2p_connector_lookup = automat.find('p2p_connector')
        if p2p_connector_lookup:
            p2p_connector_machine = automat.objects().get(p2p_connector_lookup[0])
            if p2p_connector_machine and p2p_connector_machine.state == 'CONNECTED':
                proxy_receiver_lookup = automat.find('proxy_receiver')
                if proxy_receiver_lookup:
                    proxy_receiver_machine = automat.objects().get(proxy_receiver_lookup[0])
                    if proxy_receiver_machine and proxy_receiver_machine.state == 'LISTEN':
                        # service_proxy_transport() is enabled, proxy_receiver() is listening: all good
                        wait_timeout_defer = Deferred()
                        wait_timeout_defer.addBoth(lambda _: ret.callback(OK({
                            'service_network': 'started',
                            'service_gateway': 'started',
                            'service_p2p_hookups': 'started',
                            'service_proxy_transport': 'started',
                            'proxy_receiver_state': proxy_receiver_machine.state,
                        }, api_method='network_connected')))
                        wait_timeout_defer.addTimeout(wait_timeout, clock=reactor)
                        return ret
                else:
                    # service_proxy_transport() is enabled, but proxy_receiver() is not ready yet: must wait a bit
#                     wait_timeout_defer = Deferred()
#                     wait_timeout_defer.addBoth(lambda _: ret.callback(OK({
#                         'service_network': 'started',
#                         'service_gateway': 'started',
#                         'service_p2p_hookups': 'started',
#                         'service_proxy_transport': 'not started',
#                         'p2p_connector_state': p2p_connector_machine.state,
#                     }, api_method='network_connected')))
#                     wait_timeout_defer.addTimeout(wait_timeout, clock=reactor)
#                     return ret
                    lg.warn('disconnected, reason is proxy_receiver() not started yet')
                    ret.callback(ERROR('disconnected', reason='proxy_receiver_not_started', api_method='network_connected'))
                    return ret

    if not my_id.isLocalIdentityReady():
        lg.warn('local identity is not valid or not exist')
        return ERROR('local identity is not valid or not exist', reason='identity_not_exist')
    if not driver.is_enabled('service_network'):
        lg.warn('service_network() is disabled')
        return ERROR('service_network() is disabled', reason='service_network_disabled')
    if not driver.is_enabled('service_gateway'):
        lg.warn('service_gateway() is disabled')
        return ERROR('service_gateway() is disabled', reason='service_gateway_disabled')
    if not driver.is_enabled('service_p2p_hookups'):
        lg.warn('service_p2p_hookups() is disabled')
        return ERROR('service_p2p_hookups() is disabled', reason='service_p2p_hookups_disabled')

    def _do_p2p_connector_test():
        if _Debug:
            lg.dbg(_DebugLevel, 'checking p2p_connector')
        try:
            p2p_connector_lookup = automat.find('p2p_connector')
            if not p2p_connector_lookup:
                lg.warn('disconnected, reason is "p2p_connector_not_found"')
                ret.callback(ERROR('disconnected', reason='p2p_connector_not_found', api_method='network_connected'))
                return None
            p2p_connector_machine = automat.objects().get(p2p_connector_lookup[0])
            if not p2p_connector_machine:
                lg.warn('disconnected, reason is "p2p_connector_not_exist"')
                ret.callback(ERROR('disconnected', reason='p2p_connector_not_exist', api_method='network_connected'))
                return None
            if p2p_connector_machine.state in ['DISCONNECTED', ]:
                lg.warn('disconnected, reason is "p2p_connector_disconnected", sending "check-synchronize" event to p2p_connector()')
                p2p_connector_machine.automat('check-synchronize')
                ret.callback(ERROR('disconnected', reason='p2p_connector_disconnected', api_method='network_connected'))
                return None
            # ret.callback(OK('connected'))
            _do_service_proxy_transport_test()
        except:
            lg.exc()
            ret.callback(ERROR('disconnected', reason='p2p_connector_error', api_method='network_connected'))
        return None

    def _do_service_proxy_transport_test():
        if _Debug:
            lg.dbg(_DebugLevel, 'checking proxy_transport')
        if not driver.is_enabled('service_proxy_transport'):
            ret.callback(OK({
                'service_network': 'started',
                'service_gateway': 'started',
                'service_p2p_hookups': 'started',
                'service_proxy_transport': 'disabled',
            }, api_method='network_connected'))
            return None
        try:
            proxy_receiver_lookup = automat.find('proxy_receiver')
            if not proxy_receiver_lookup:
                lg.warn('disconnected, reason is "proxy_receiver_not_found"')
                ret.callback(ERROR('disconnected', reason='proxy_receiver_not_found', api_method='network_connected'))
                return None
            proxy_receiver_machine = automat.objects().get(proxy_receiver_lookup[0])
            if not proxy_receiver_machine:
                lg.warn('disconnected, reason is "proxy_receiver_not_exist"')
                ret.callback(ERROR('disconnected', reason='proxy_receiver_not_exist', api_method='network_connected'))
                return None
            if proxy_receiver_machine.state != 'LISTEN':
                lg.warn('disconnected, reason is "proxy_receiver_disconnected", sending "start" event to proxy_receiver()')
                proxy_receiver_machine.automat('start')
                ret.callback(ERROR('disconnected', reason='proxy_receiver_disconnected', api_method='network_connected'))
                return None
            ret.callback(OK({
                'service_network': 'started',
                'service_gateway': 'started',
                'service_p2p_hookups': 'started',
                'service_proxy_transport': 'started',
                'proxy_receiver_state': proxy_receiver_machine.state,
            }, api_method='network_connected'))
        except:
            lg.exc()
            ret.callback(ERROR('disconnected', reason='proxy_receiver_error', api_method='network_connected'))
        return None

    def _on_service_restarted(resp, service_name):
        if _Debug:
            lg.args(_DebugLevel, resp=resp, service_name=service_name)
        if service_name == 'service_network':
            _do_service_test('service_gateway')
        elif service_name == 'service_gateway':
            _do_service_test('service_p2p_hookups')
        else:
            _do_p2p_connector_test()
        return resp

    def _do_service_restart(service_name):
        if _Debug:
            lg.args(_DebugLevel, service_name=service_name)
        d = service_restart(service_name, wait_timeout=wait_timeout)
        d.addCallback(_on_service_restarted, service_name)
        d.addErrback(lambda err: ret.callback(dict(
            list(ERROR(err, api_method='network_connected').items()) + list({'reason': '{}_restart_error'.format(service_name)}.items()))))
        return None

    def _do_service_test(service_name):
        if _Debug:
            lg.args(_DebugLevel, service_name=service_name)
        try:
            svc_info = service_info(service_name)
            svc_state = svc_info['result']['state']
        except:
            lg.exc('service "%s" test failed' % service_name)
            ret.callback(ERROR(
                'disconnected',
                reason='{}_info_error'.format(service_name),
                api_method='network_connected',
            ))
            return None
        if svc_state != 'ON':
            _do_service_restart(service_name)
            return None
        if service_name == 'service_network':
            reactor.callLater(0, _do_service_test, 'service_gateway')  # @UndefinedVariable
        elif service_name == 'service_gateway':
            reactor.callLater(0, _do_service_test, 'service_p2p_hookups')  # @UndefinedVariable
        elif service_name == 'service_p2p_hookups':
            reactor.callLater(0, _do_p2p_connector_test)  # @UndefinedVariable
        elif service_name == 'service_proxy_transport':
            reactor.callLater(0, _do_service_proxy_transport_test)  # @UndefinedVariable
        else:
            raise Exception('unknown service to test %s' % service_name)
        return None

    _do_service_test('service_network')
    return ret


def network_status(show_suppliers=True, show_customers=True, show_cache=True,
                   show_tcp=True, show_udp=True, show_proxy=True, show_dht=True):
    """
    """
    if not driver.is_on('service_network'):
        return ERROR('service_network() is not started')
    from automats import automat
    from lib import net_misc
    from main import settings
    from userid import my_id
    from userid import global_id

    r = {
        'p2p_connector_state': None,
        'network_connector_state': None,
        'idurl': None,
        'global_id': None,
    }
    p2p_connector_lookup = automat.find('p2p_connector')
    if p2p_connector_lookup:
        p2p_connector_machine = automat.objects().get(p2p_connector_lookup[0])
        if p2p_connector_machine:
            r['p2p_connector_state'] = p2p_connector_machine.state
    network_connector_lookup = automat.find('network_connector')
    if network_connector_lookup:
        network_connector_machine = automat.objects().get(network_connector_lookup[0])
        if network_connector_machine:
            r['network_connector_state'] = network_connector_machine.state
    if my_id.isLocalIdentityReady():
        r['idurl'] = my_id.getLocalID()
        r['global_id'] = my_id.getGlobalID()
        r['identity_sources'] = my_id.getLocalIdentity().getSources(as_originals=True)
        r['identity_contacts'] = my_id.getLocalIdentity().getContacts()
    if True in [show_suppliers, show_customers, show_cache, ] and driver.is_on('service_p2p_hookups'):
        from contacts import contactsdb
        from p2p import online_status
        if show_suppliers:
            connected = 0
            items = []
            for idurl in contactsdb.all_suppliers():
                i = {
                    'idurl': idurl,
                    'global_id': global_id.UrlToGlobalID(idurl),
                    'state': None
                }
                inst = online_status.getInstance(idurl)
                if inst:
                    i['state'] = inst.state
                    if inst.state == 'CONNECTED':
                        connected += 1
                items.append(i)
            r['suppliers'] = {
                'desired': settings.getSuppliersNumberDesired(),
                'requested': contactsdb.num_suppliers(),
                'connected': connected,
                'total': contactsdb.total_suppliers(),
                'peers': items,
            }
        if show_customers:
            connected = 0
            items = []
            for idurl in contactsdb.customers():
                i = {
                    'idurl': idurl,
                    'global_id': global_id.UrlToGlobalID(idurl),
                    'state': None
                }
                inst = online_status.getInstance(idurl)
                if inst:
                    i['state'] = inst.state
                    if inst.state == 'CONNECTED':
                        connected += 1
                items.append(i)
            r['customers'] = {
                'connected': connected,
                'total': contactsdb.num_customers(),
                'peers': items,
            }
        if show_cache:
            from contacts import identitycache
            connected = 0
            items = []
            for idurl in identitycache.Items().keys():
                i = {
                    'idurl': idurl,
                    'global_id': global_id.UrlToGlobalID(idurl),
                    'state': None
                }
                inst = online_status.getInstance(idurl)
                if inst:
                    i['state'] = inst.state
                    if inst.state == 'CONNECTED':
                        connected += 1
                items.append(i)
            r['cache'] = {
                'total': identitycache.CacheLen(),
                'connected': connected,
                'peers': items,
            }
    if True in [show_tcp, show_udp, show_proxy, ]:
        from transport import gateway
        if show_tcp:
            r['tcp'] = {
                'sessions': [],
                'streams': [],
            }
            if driver.is_on('service_tcp_transport'):
                sessions = []
                for s in gateway.list_active_sessions('tcp'):
                    i = {
                        'peer': getattr(s, 'peer', None),
                        'state': getattr(s, 'state', None),
                        'id': getattr(s, 'id', None),
                        'idurl': getattr(s, 'peer_idurl', None),
                        'address': net_misc.pack_address_text(getattr(s, 'peer_address', None)),
                        'external_address': net_misc.pack_address_text(getattr(s, 'peer_external_address', None)),
                        'connection_address': net_misc.pack_address_text(getattr(s, 'connection_address', None)),
                        'bytes_received': getattr(s, 'total_bytes_received', 0),
                        'bytes_sent': getattr(s, 'total_bytes_sent', 0),
                    }
                    sessions.append(i)
                streams = []
                for s in gateway.list_active_streams('tcp'):
                    i = {
                        'started': s.started,
                        'stream_id': s.file_id,
                        'transfer_id': s.transfer_id,
                        'size': s.size,
                        'type': s.typ,
                    }
                    streams.append(i)
                r['tcp']['sessions'] = sessions
                r['tcp']['streams'] = streams
        if show_udp:
            from lib import udp
            r['udp'] = {
                'sessions': [],
                'streams': [],
                'ports': [],
            }
            for one_listener in udp.listeners().values():
                r['udp']['ports'].append(one_listener.port)
            if driver.is_on('service_udp_transport'):
                sessions = []
                for s in gateway.list_active_sessions('udp'):
                    sessions.append({
                        'peer': s.peer_id,
                        'state': s.state,
                        'id': s.id,
                        'idurl': s.peer_idurl,
                        'address': net_misc.pack_address_text(s.peer_address),
                        'bytes_received': s.bytes_sent,
                        'bytes_sent': s.bytes_received,
                        'outgoing': len(s.file_queue.outboxFiles),
                        'incoming': len(s.file_queue.inboxFiles),
                        'queue': len(s.file_queue.outboxQueue),
                        'dead_streams': len(s.file_queue.dead_streams),
                    })
                streams = []
                for s in gateway.list_active_streams('udp'):
                    streams.append({
                        'started': s.started,
                        'stream_id': s.stream_id,
                        'transfer_id': s.transfer_id,
                        'size': s.size,
                        'type': s.typ,
                    })
                r['udp']['sessions'] = sessions
                r['udp']['streams'] = streams
        if show_proxy:
            r['proxy'] = {
                'sessions': [],
            }
            if driver.is_on('service_proxy_transport'):
                sessions = []
                for s in gateway.list_active_sessions('proxy'):
                    i = {
                        'state': s.state,
                        'id': s.id,
                    }
                    if getattr(s, 'router_proto_host', None):
                        i['proto'] = s.router_proto_host[0]
                        i['peer'] = s.router_proto_host[1]
                    if getattr(s, 'router_idurl', None):
                        i['idurl'] = s.router_idurl
                        i['router'] = global_id.UrlToGlobalID(s.router_idurl)
                    if getattr(s, 'traffic_out', None):
                        i['bytes_sent'] = s.traffic_out
                    if getattr(s, 'traffic_in', None):
                        i['bytes_received'] = s.traffic_in
                    if getattr(s, 'pending_packets', None):
                        i['queue'] = len(s.pending_packets)
                    sessions.append(i)
                r['proxy']['sessions' ] = sessions
    if show_dht:
        from dht import dht_service
        r['dht'] = {}
        if driver.is_on('service_entangled_dht'):
            layers = []
            for layer_id in sorted(dht_service.node().layers):
                layers.append({
                    'layer_id': layer_id,
                    'data_store_items': len(dht_service.node()._dataStores[layer_id].keys()),
                    'node_items': len(dht_service.node().data.get(layer_id, {})),
                    'node_id': dht_service.node().layers[layer_id],
                    'buckets': len(dht_service.node()._routingTables[layer_id]._buckets),
                    'contacts': dht_service.node()._routingTables[layer_id].totalContacts(),
                    'attached': (layer_id in dht_service.node().attached_layers),
                    'active': (layer_id in dht_service.node().active_layers),
                    'packets_received': dht_service.node().packets_in.get(layer_id, 0),
                    'packets_sent': dht_service.node().packets_out.get(layer_id, 0),
                    'rpc_calls': dht_service.node().rpc_calls.get(layer_id, {}),
                    'rpc_responses': dht_service.node().rpc_responses.get(layer_id, {}),
                })
            r['dht'].update({
                'udp_port': dht_service.node().port,
                'bytes_received': dht_service.node().bytes_in,
                'bytes_sent': dht_service.node().bytes_out,
                'layers': layers,
            })
    return OK(r)


def network_configuration():
    return OK(driver.get_network_configuration())

#------------------------------------------------------------------------------

def dht_node_find(node_id_64=None, layer_id=0):
    if not driver.is_on('service_entangled_dht'):
        return ERROR('service_entangled_dht() is not started')
    from dht import dht_service
    if node_id_64 is None:
        node_id = dht_service.random_key()
        node_id_64 = node_id
    else:
        node_id = node_id_64
    ret = Deferred()

    def _cb(response):
        try:
            if isinstance(response, list):
                return ret.callback(OK({
                    'my_dht_id': dht_service.node().layers[0],
                    'lookup': node_id_64, 
                    'closest_nodes': [{
                        'dht_id': c.id,
                        'address': '%s:%d' % (strng.to_text(c.address, errors='ignore'), c.port),
                    } for c in response],
                }, api_method='dht_node_find'))
            return ret.callback(ERROR('unexpected DHT response', api_method='dht_node_find'))
        except Exception as exc:
            lg.exc()
            return ret.callback(ERROR(exc, api_method='dht_node_find'))

    def _eb(err):
        lg.err(err)
        ret.callback(ERROR(err, api_method='dht_node_find'))
        return None

    d = dht_service.find_node(node_id, layer_id=layer_id)
    d.addCallback(_cb)
    d.addErrback(_eb)
    return ret


def dht_user_random(layer_id=0, count=1):
    if not driver.is_on('service_nodes_lookup'):
        return ERROR('service_nodes_lookup() is not started')
    from p2p import lookup
    ret = Deferred()

    def _cb(idurls):
        if not idurls:
            ret.callback(ERROR('no users found', api_method='dht_user_random'))
            return None
        return ret.callback(RESULT(result=idurls, api_method='dht_user_random'))

    def _eb(err):
        lg.err(err)
        ret.callback(ERROR(err, api_method='dht_user_random'))
        return None

    def _process(idurl, node):
        result = Deferred()
        result.callback(idurl)
        return result

    tsk = lookup.start(
        count=count,
        layer_id=layer_id,
        consume=True,
        force_discovery=True,
        process_method=_process,
    )
    tsk.result_defer.addCallback(_cb)
    tsk.result_defer.addErrback(_eb)
    return ret


def dht_value_get(key, record_type='skip_validation', layer_id=0, use_cache_ttl=None):
    if not driver.is_on('service_entangled_dht'):
        return ERROR('service_entangled_dht() is not started')
    from dht import dht_service
    from dht import dht_records
    ret = Deferred()

    record_rules = dht_records.get_rules(record_type)
    if not record_rules:
        return ERROR('record must be have correct type and known validation rules')

    def _cb(value):
        if isinstance(value, dict):
            if _Debug:
                lg.out(_DebugLevel, 'api.dht_value_get OK: %r' % value)
            return ret.callback(OK({
                'read': 'success',
                'my_dht_id': dht_service.node().layers[0],
                'key': strng.to_text(key, errors='ignore'),
                'value': value,
            }, api_method='dht_value_get'))
        closest_nodes = []
        if isinstance(value, list):
            closest_nodes = value
        if _Debug:
            lg.out(_DebugLevel, 'api.dht_value_get ERROR: %r' % value)
        return ret.callback(OK({
            'read': 'failed',
            'my_dht_id': dht_service.node().layers[0],
            'key': strng.to_text(key, errors='ignore'),
            'closest_nodes': [{
                'dht_id': c.id,
                'address': '%s:%d' % (strng.to_text(c.address, errors='ignore'), c.port),
            } for c in closest_nodes],
        }, api_method='dht_value_get'))

    def _eb(err):
        lg.err(err)
        ret.callback(ERROR(err, api_method='dht_value_get'))
        return None

    d = dht_service.get_valid_data(
        key=key,
        rules=record_rules,
        raise_for_result=False,
        return_details=True,
        layer_id=layer_id,
        use_cache_ttl=use_cache_ttl,
    )
    d.addCallback(_cb)
    d.addErrback(_eb)
    return ret


def dht_value_set(key, value, expire=None, record_type='skip_validation', layer_id=0):
    if not driver.is_on('service_entangled_dht'):
        return ERROR('service_entangled_dht() is not started')

    if not isinstance(value, dict):
        try:
            value = jsn.loads(value)
        except Exception as exc:
            lg.exc()
            return ERROR('input value must be a json')
    try:
        jsn.dumps(value, indent=0, sort_keys=True, separators=(',', ':'))
    except Exception as exc:
        return ERROR(exc)

    from dht import dht_service
    from dht import dht_records
    ret = Deferred()

    record_rules = dht_records.get_rules(record_type)
    if not record_rules:
        return ERROR('record must be have correct type and known validation rules')

    def _cb(response):
        try:
            if isinstance(response, list):
                if _Debug:
                    lg.out(_DebugLevel, 'api.dht_value_set OK: %r' % response)
                return ret.callback(OK({
                    'write': 'success' if len(response) > 0 else 'failed',
                    'my_dht_id': dht_service.node().layers[0],
                    'key': strng.to_text(key, errors='ignore'),
                    'value': value,
                    'closest_nodes': [{
                        'dht_id': c.id,
                        'address': '%s:%d' % (strng.to_text(c.address, errors='ignore'), c.port),
                    } for c in response],
                }, api_method='dht_value_set'))
            if _Debug:
                lg.out(_DebugLevel, 'api.dht_value_set ERROR: %r' % response)
            return ret.callback(ERROR('unexpected DHT response', api_method='dht_value_set'))
        except Exception as exc:
            lg.exc()
            return ret.callback(ERROR(exc, api_method='dht_value_set'))

    def _eb(err):
        try:
            nodes = []
            try:
                errmsg = err.value.subFailure.getErrorMessage()
            except:
                try:
                    errmsg = err.getErrorMessage()
                except:
                    errmsg = 'store operation failed'
            try:
                nodes = err.value
            except:
                pass
            closest_nodes = []
            if nodes and isinstance(nodes, list) and hasattr(nodes[0], 'address') and hasattr(nodes[0], 'port'):
                closest_nodes = [{
                    'dht_id': c.id,
                    'address': '%s:%d' % (strng.to_text(c.address, errors='ignore'), c.port),
                } for c in nodes]
            if _Debug:
                lg.out(_DebugLevel, 'api.dht_value_set ERROR: %r' % errmsg)
            return ret.callback(ERROR(errmsg, details={
                'write': 'failed',
                'my_dht_id': dht_service.node().layers[0],
                'key': strng.to_text(key, errors='ignore'),
                'closest_nodes': closest_nodes,
            }, api_method='dht_value_set'))
        except Exception as exc:
            lg.exc()
            return ERROR(exc, api_method='dht_value_set')

    d = dht_service.set_valid_data(
        key=key,
        json_data=value,
        expire=expire or dht_service.KEY_EXPIRE_MAX_SECONDS,
        rules=record_rules,
        collect_results=True,
        layer_id=layer_id,
    )
    d.addCallback(_cb)
    d.addErrback(_eb)
    return ret


def dht_local_db_dump():
    if not driver.is_on('service_entangled_dht'):
        return ERROR('service_entangled_dht() is not started')
    from dht import dht_service
    return RESULT(dht_service.dump_local_db(value_as_json=True))

#------------------------------------------------------------------------------

def automats_list():
    """
    Returns a list of all currently running state machines.

    This is a very useful method when you need to investigate a problem in the software.

    ###### HTTP
        curl -X GET 'localhost:8180/automat/list/v1'

    ###### WebSocket
        websocket.send('{"command": "api_call", "method": "automats_list", "kwargs": {} }');
    """
    from automats import automat
    result = [{
        'index': a.index,
        'name': a.name,
        'state': a.state,
        'timers': (','.join(list(a.getTimers().keys()))),
    } for a in automat.objects().values()]
    if _Debug:
        lg.out(_DebugLevel, 'api.automats_list responded with %d items' % len(result))
    return RESULT(result)

#------------------------------------------------------------------------------
