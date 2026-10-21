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

"""Module for the entry points of the installed distributions."""

import sys

if sys.version_info >= (3, 8):
    import importlib.metadata as importlib_metadata
else:
    import importlib_metadata

_entry_points = None


def select_entry_points(group):
    """
    Return the entry points of a group.

    The installed distributions are scanned once per process, because one scan reads the
    metadata of every distribution on the path and launch looks up several groups.
    """
    global _entry_points
    if _entry_points is None:
        _entry_points = importlib_metadata.entry_points()
    if hasattr(_entry_points, 'select'):
        return _entry_points.select(group=group)
    return _entry_points.get(group, [])
