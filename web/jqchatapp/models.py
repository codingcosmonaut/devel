#!/usr/bin/env python
# models.py
#
# Copyright (C) 2008-2016 Veselin Penev, http://bitdust.io
#
# This file (models.py) is part of BitDust Software.
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
# -*- coding: utf-8 -*-

import datetime
import time

#------------------------------------------------------------------------------

import warnings
import exceptions
warnings.filterwarnings("ignore", category=exceptions.RuntimeWarning)

#------------------------------------------------------------------------------

from django.db import models
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.conf import settings

#------------------------------------------------------------------------------

from lib import nameurl

from contacts import contactsdb

#------------------------------------------------------------------------------

# The list of events can be customized for each project.
try:
    EVENT_CHOICES = settings.JQCHAT_EVENT_CHOICES
except:
    EVENT_CHOICES = (
        (1, "has changed the room's description."),
        (2, "has joined the room"),
        (3, "has left the room"),
    )

#------------------------------------------------------------------------------


class Room(models.Model):
    idurl = models.URLField(max_length=255)
    name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Name of the room.')
    created = models.DateTimeField(editable=False)
    description = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text='The description of this room.')
    last_activity = models.IntegerField(
        editable=False,
        help_text='Last activity in the room. Stored as a Unix timestamp.')
    content_type = models.ForeignKey(ContentType, blank=True, null=True)
    object_id = models.PositiveIntegerField(blank=True, null=True)
    content_object = generic.GenericForeignKey()

    def __unicode__(self):
        return u'%s' % (self.name)

    class Meta:
        ordering = ['created']

    def __init__(self, *args, **kw):
        super(Room, self).__init__(*args, **kw)
        self._init_description = self.description

    def save(self, **kw):
        if not self.last_activity:
            self.last_activity = time.time()
        if not self.created:
            self.created = datetime.datetime.now()
        super(Room, self).save(**kw)

    @property
    def last_activity_formatted(self):
        return display_timestamp(self.last_activity)

    @property
    def last_activity_datetime(self):
        return datetime.datetime.fromtimestamp(self.last_activity)

#------------------------------------------------------------------------------


class messageManager(models.Manager):

    def create_message(self, idurl, room, msg):
        name = contactsdb.get_correspondent_nickname(
            idurl) or nameurl.GetName(idurl)
        m = Message.objects.create(
            idurl=idurl,
            room=room,
            # text='<strong>%s</strong> %s<br />' % (user, msg)
            text='<span class=chatname>%s</span><span class=chattext>%s</span>' % (
                name, msg))
        return m

    def create_event(self, idurl, room, event_id):
        name = contactsdb.get_correspondent_nickname(
            idurl) or nameurl.GetName(idurl)
        m = Message(
            idurl=idurl,
            room=room,
            event=event_id)
        # m.text = "<strong>%s</strong><em class=event>%s</em><br />" % (user, m.get_event_display())
        m.text = '<span class=chatname>%s</span><span class=chatevent>%s</span>' % (
            name, m.get_event_display())
        m.save()
        return m

#------------------------------------------------------------------------------


class Message(models.Model):
    idurl = models.URLField(max_length=255)
    room = models.ForeignKey(
        Room, help_text='This message was posted in a given chat room.')
    event = models.IntegerField(
        null=True,
        blank=True,
        choices=EVENT_CHOICES,
        help_text='An action performed in the room, either by a user or by the system (e.g. XYZ leaves room.')
    text = models.TextField(
        null=True,
        blank=True,
        help_text='A message, either typed in by a user or generated by the system.')
    unix_timestamp = models.FloatField(
        editable=False,
        help_text='Unix timestamp when this message was inserted into the database.')
    created = models.DateTimeField(editable=False)

    def __unicode__(self):
        return u'%s, %s' % (self.user, self.unix_timestamp)

    def save(self, **kw):
        if not self.unix_timestamp:
            self.unix_timestamp = time.time()
            self.created = datetime.datetime.fromtimestamp(self.unix_timestamp)
        super(Message, self).save(**kw)
        self.room.last_activity = int(time.time())
        self.room.save()

    class Meta:
        ordering = ['unix_timestamp']

    objects = messageManager()

#------------------------------------------------------------------------------


class memberManager(models.Manager):

    def remove_member(self, idurl, room):
        usr_prev_rooms = RoomMember.objects.filter(idurl=idurl)
        for prev_room in usr_prev_rooms:
            if prev_room.room == room:
                continue
            Message.objects.create_event(idurl, prev_room.room, 3)
        usr_prev_rooms.delete()

    def create_member(self, idurl, room):
        self.remove_member(idurl, room)
        Message.objects.create_event(idurl, room, 2)
        m = RoomMember.objects.create(idurl=idurl,
                                      # name=name,
                                      room=room)
        return m

#------------------------------------------------------------------------------


class RoomMember(models.Model):
    room = models.ForeignKey(Room, null=True)
    idurl = models.URLField(max_length=255)
    # name = models.URLField(max_length=255)

    def save(self, **kw):
        super(RoomMember, self).save(**kw)

    class Meta:
        ordering = ['idurl', ]

    objects = memberManager()

#------------------------------------------------------------------------------


def display_timestamp(t):
    return '%s (%s)' % (t, time.strftime('%d/%m/%Y %H:%M', time.gmtime(t)))
