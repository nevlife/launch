# Copyright 2019 Open Source Robotics Foundation, Inc.
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

"""Test the abstract Parser class."""

from unittest.mock import patch
import warnings

import launch.frontend.parser
from launch.frontend.parser import Parser
from launch.utilities import entry_points_impl
from launch.utilities.entry_points_impl import importlib_metadata

import pytest


class InvalidEntryPoint:

    name = 'RefusesToLoad'

    def load(self):
        raise ValueError('I dont want to load!')


def skip_if_warned_already(warn_text):
    # TODO(sloretz) clear warning registry instead of skipping
    if hasattr(launch.frontend.parser, '__warningregistry__'):
        for key in launch.frontend.parser.__warningregistry__.keys():
            if warn_text in key[0]:
                pytest.skip('Skip because warnings can only be raised once')


def test_invalid_launch_extension(monkeypatch):
    skip_if_warned_already('Failed to load the launch')
    monkeypatch.setattr(entry_points_impl, '_entry_points', None)
    monkeypatch.setattr(Parser, 'extensions_loaded', False)
    with patch(importlib_metadata.__name__ + '.entry_points') as mock_ep:
        mock_ep.return_value = {
            'launch.frontend.launch_extension': [InvalidEntryPoint()]
        }
        with warnings.catch_warnings(record=True) as caught_warnings:
            Parser.load_launch_extensions()
            assert caught_warnings
            assert 'Failed to load the launch' in str(caught_warnings[0])


def test_invalid_parser_implementations(monkeypatch):
    skip_if_warned_already('Failed to load the parser')
    monkeypatch.setattr(entry_points_impl, '_entry_points', None)
    monkeypatch.setattr(Parser, 'frontend_parsers', None)
    with patch(importlib_metadata.__name__ + '.entry_points') as mock_ep:
        mock_ep.return_value = {
            'launch.frontend.parser': [InvalidEntryPoint()]
        }

        with warnings.catch_warnings(record=True) as caught_warnings:
            Parser.load_parser_implementations()
            assert caught_warnings
            assert 'Failed to load the parser' in str(caught_warnings[0])


def test_entry_points_scanned_once(monkeypatch):
    monkeypatch.setattr(entry_points_impl, '_entry_points', None)
    monkeypatch.setattr(Parser, 'extensions_loaded', False)
    monkeypatch.setattr(Parser, 'frontend_parsers', None)
    with patch(importlib_metadata.__name__ + '.entry_points') as mock_ep:
        mock_ep.return_value = {}
        Parser.load_launch_extensions()
        Parser.load_parser_implementations()
        assert entry_points_impl.select_entry_points('launch_ros.node_action') == []
    assert mock_ep.call_count == 1
