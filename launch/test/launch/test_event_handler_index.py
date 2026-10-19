# Copyright 2026 Open Source Robotics Foundation, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the event handler index in LaunchContext."""

from launch import LaunchContext
from launch.event import Event
from launch.event_handler import EventHandler


class EventA(Event):
    name = 'EventA'


class EventB(Event):
    name = 'EventB'


class EventAB(EventA, EventB):
    name = 'EventAB'


class ActionEvent(Event):
    name = 'ActionEvent'

    def __init__(self, action):
        self.action = action


def _all_handlers_that_match(context, event):
    return [h for h in context._event_handlers if h.matches(event)]


def _handler(event_type=None, action=None):
    def matcher(event):
        if event_type is not None and not isinstance(event, event_type):
            return False
        return action is None or getattr(event, 'action', None) is action
    handler = EventHandler(
        matcher=matcher, event_types=None if event_type is None else (event_type,))
    handler.event_action = action
    return handler


def test_index_keeps_deque_order_and_matches():
    context = LaunchContext()
    first, second = object(), object()
    handlers = [
        _handler(), _handler(EventA), _handler(EventB), _handler(ActionEvent, first),
        _handler(ActionEvent, second), _handler(ActionEvent), _handler(EventAB),
    ]
    for i, handler in enumerate(handlers):
        context.register_event_handler(handler, append=bool(i % 2))
    events = [EventA(), EventB(), EventAB(), ActionEvent(first), ActionEvent(second),
              ActionEvent(None)]
    for event in events:
        candidates = context._event_handlers_for(event)
        assert [h for h in candidates if h.matches(event)] == \
            _all_handlers_that_match(context, event)
    context.unregister_event_handler(handlers[3])
    context.unregister_event_handler(handlers[0])
    for event in events:
        candidates = context._event_handlers_for(event)
        assert [h for h in candidates if h.matches(event)] == \
            _all_handlers_that_match(context, event)


def test_handler_with_several_types_is_returned_once():
    context = LaunchContext()
    handler = EventHandler(matcher=lambda event: True, event_types=(EventA, EventB))
    context.register_event_handler(handler)
    assert context._event_handlers_for(EventAB()) == [handler]


def test_handler_registered_twice_is_unregistered_once():
    context = LaunchContext()
    handler = _handler(EventA)
    context.register_event_handler(handler)
    context.register_event_handler(handler, append=True)
    context.unregister_event_handler(handler)
    assert context._event_handlers_for(EventA()) == [handler]
    context.unregister_event_handler(handler)
    assert context._event_handlers_for(EventA()) == []
