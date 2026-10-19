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

"""Tests for the launch.logging module."""

import logging
import os
import pathlib
import re
from unittest import mock

import launch.logging

import pytest


@pytest.fixture
def log_dir(tmpdir_factory):
    """Test fixture that generates a temporary directory for log files."""
    return str(tmpdir_factory.mktemp('logs'))


@pytest.fixture
def mock_clean_env(monkeypatch):
    monkeypatch.delenv('OVERRIDE_LAUNCH_SCREEN_FORMAT', raising=False)
    monkeypatch.delenv('OVERRIDE_LAUNCH_LOG_FORMAT', raising=False)


def test_bad_logging_launch_config(mock_clean_env):
    """Tests that setup throws at bad configuration."""
    launch.logging.reset()

    with pytest.raises(ValueError):
        launch.logging.launch_config.log_dir = 'not/a/real/dir'

    with pytest.raises(ValueError):
        launch.logging.launch_config.set_screen_format('default', screen_style='%')

    with pytest.raises(ValueError):
        launch.logging.launch_config.set_log_format(log_format='default', log_style='%')


def test_process_output_screen_batch(capsys, mock_clean_env):
    """Batch complete lines without changing screen text."""
    launch.logging.reset()
    logger, _ = launch.logging.get_output_loggers('batch', 'screen')
    with mock.patch.object(logger, 'info', wraps=logger.info) as info:
        launch.logging._log_process_output(logger, ['[batch] one', '[batch] two', ''])
    assert capsys.readouterr().out == '[batch] one\n[batch] two\n\n'
    info.assert_called_once_with('[batch] one\n[batch] two\n')


@pytest.mark.parametrize('customization', ['filter', 'handler', 'formatter', 'factory', 'log'])
def test_process_output_records(capsys, log_dir, mock_clean_env, customization):
    """Keep per-line records for logging customizations and files."""
    launch.logging.reset()
    launch.logging.launch_config.log_dir = log_dir
    output = 'both' if customization == 'log' else 'screen'
    logger, _ = launch.logging.get_output_loggers('records', output)
    screen = launch.logging.launch_config.get_screen_handler()
    if customization == 'filter':
        logger.addFilter(lambda record: record.msg != 'two')
    elif customization == 'handler':
        logger.addHandler(logging.NullHandler())
    elif customization == 'formatter':
        screen.setFormatterFor(logger, logging.Formatter('custom: {msg}', style='{'))
    factory = logging.getLogRecordFactory()
    if customization == 'factory':
        logging.setLogRecordFactory(lambda *args, **kwargs: factory(*args, **kwargs))
    try:
        with mock.patch.object(logger, 'info', wraps=logger.info) as info:
            launch.logging._log_process_output(logger, ['one', 'two'])
        assert info.call_args_list == [mock.call('one'), mock.call('two')]
        expected = 'one\n' if customization == 'filter' else 'one\ntwo\n'
        if customization == 'formatter':
            expected = 'custom: one\ncustom: two\n'
        assert capsys.readouterr().out == expected
        if customization == 'log':
            lines = pathlib.Path(log_dir, 'launch.log').read_text().splitlines()
            assert len(lines) == 2
            assert lines[0].endswith(' one') and lines[1].endswith(' two')
    finally:
        logging.setLogRecordFactory(factory)
        logger.filters.clear()


def test_output_loggers_bad_configuration(log_dir):
    """Tests that output loggers setup throws at bad configuration."""
    launch.logging.launch_config.reset()

    launch.logging.launch_config.log_dir = log_dir

    with pytest.raises(ValueError):
        launch.logging.get_output_loggers('some-proc', 'not_an_alias')

    with pytest.raises(ValueError):
        launch.logging.get_output_loggers('some-proc', {'garbage': {'log'}})

    with pytest.raises(ValueError):
        launch.logging.get_output_loggers('some-proc', {'stdout': {'garbage'}})


@pytest.mark.parametrize('config,checks', [
    ('screen', {'stdout': {'screen'}, 'stderr': {'screen'}}),
    ('log', {'stdout': {'log'}, 'stderr': {'log', 'screen'}}),
    ('both', {'both': {'log', 'screen'}}),
    ('own_log', {
        'stdout': {'own_log'},
        'stderr': {'own_log'},
        'both': {'own_log'},
    }),
    ('full', {
        'stdout': {'log', 'own_log', 'screen'},
        'stderr': {'log', 'own_log', 'screen'},
        'both': {'own_log'},
    }),
    (
        {'stdout': {'screen', 'log'}, 'stderr': {'own_log'}},
        {
            'stdout': {'screen', 'log'},
            'stderr': {'own_log'}
        },
    )
])
def test_output_loggers_configuration(capsys, log_dir, config, checks, mock_clean_env):
    checks = {'stdout': set(), 'stderr': set(), 'both': set(), **checks}
    launch.logging.reset()
    launch.logging.launch_config.log_dir = log_dir
    logger = launch.logging.get_logger('some-proc')
    logger.addHandler(launch.logging.launch_config.get_screen_handler())
    logger.addHandler(launch.logging.launch_config.get_log_file_handler())
    logger.setLevel(logging.ERROR)
    stdout_logger, stderr_logger = launch.logging.get_output_loggers('some-proc', config)

    logger.debug('oops')
    logger.error('baz')
    stdout_logger.info('foo')
    stderr_logger.info('bar')

    capture = capsys.readouterr()
    lines = list(reversed(capture.out.splitlines()))
    assert '[ERROR] [some-proc]: baz' == lines.pop()
    if 'screen' in (checks['stdout'] | checks['both']):
        assert 'foo' == lines.pop()
    if 'screen' in (checks['stderr'] | checks['both']):
        assert 'bar' == lines.pop()
    assert 0 == len(lines)
    assert 0 == len(capture.err)

    launch.logging.launch_config.get_log_file_handler().flush()
    main_log_path = launch.logging.launch_config.get_log_file_path()
    assert os.path.exists(main_log_path)
    assert 0 != os.stat(main_log_path).st_size
    with open(main_log_path, 'r') as f:
        lines = list(reversed(f.readlines()))
        assert re.match(r'[0-9]+\.[0-9]+ \[ERROR\] \[some-proc\]: baz', lines.pop()) is not None
        if 'log' in (checks['stdout'] | checks['both']):
            assert re.match(r'[0-9]+\.[0-9]+ foo', lines.pop()) is not None
        if 'log' in (checks['stderr'] | checks['both']):
            assert re.match(r'[0-9]+\.[0-9]+ bar', lines.pop()) is not None
        assert 0 == len(lines)

    if 'own_log' in (checks['stdout'] | checks['both']):
        launch.logging.launch_config.get_log_file_handler('some-proc-stdout.log').flush()
        own_log_path = launch.logging.launch_config.get_log_file_path('some-proc-stdout.log')
        assert os.path.exists(own_log_path)
        assert 0 != os.stat(own_log_path).st_size
        with open(own_log_path, 'r') as f:
            lines = f.read().splitlines()
            assert 1 == len(lines)
            assert 'foo' == lines[0]
    else:
        own_log_path = launch.logging.launch_config.get_log_file_path('some-proc-stdout.log')
        assert (not os.path.exists(own_log_path) or 0 == os.stat(own_log_path).st_size)

    if 'own_log' in (checks['stderr'] | checks['both']):
        launch.logging.launch_config.get_log_file_handler('some-proc-stderr.log').flush()
        own_log_path = launch.logging.launch_config.get_log_file_path('some-proc-stderr.log')
        assert os.path.exists(own_log_path)
        assert 0 != os.stat(own_log_path).st_size
        with open(own_log_path, 'r') as f:
            lines = f.read().splitlines()
            assert 1 == len(lines)
            assert 'bar' == lines[0]
    else:
        own_log_path = launch.logging.launch_config.get_log_file_path('some-proc-stderr.log')
        assert (not os.path.exists(own_log_path) or 0 == os.stat(own_log_path).st_size)

    if 'own_log' in checks['both']:
        launch.logging.launch_config.get_log_file_handler('some-proc.log').flush()
        own_log_path = launch.logging.launch_config.get_log_file_path('some-proc.log')
        assert os.path.exists(own_log_path)
        assert 0 != os.stat(own_log_path).st_size
        with open(own_log_path, 'r') as f:
            lines = f.read().splitlines()
            assert 2 == len(lines)
            assert 'foo' == lines[0]
            assert 'bar' == lines[1]
    else:
        own_log_path = launch.logging.launch_config.get_log_file_path('some-proc.log')
        assert (not os.path.exists(own_log_path) or 0 == os.stat(own_log_path).st_size)


def test_screen_default_format_with_timestamps(capsys, log_dir, mock_clean_env):
    """Test screen logging when using the default logs format with timestamps."""
    launch.logging.reset()
    launch.logging.launch_config.level = logging.DEBUG
    launch.logging.launch_config.log_dir = log_dir
    launch.logging.launch_config.set_screen_format('default_with_timestamp')
    logger = launch.logging.get_logger('some-proc')
    logger.addHandler(launch.logging.launch_config.get_screen_handler())
    assert logger.getEffectiveLevel() == logging.DEBUG

    logger.debug('foo')

    capture = capsys.readouterr()
    lines = capture.out.splitlines()
    assert 1 == len(lines)
    assert re.match(r'[0-9]+\.[0-9]+ \[DEBUG\] \[some-proc\]: foo', lines[0]) is not None
    assert 0 == len(capture.err)


def test_screen_default_format(capsys, mock_clean_env):
    """Test screen logging when using the default logs format."""
    launch.logging.reset()

    logger = launch.logging.get_logger('some-proc')
    logger.addHandler(launch.logging.launch_config.get_screen_handler())
    assert logger.getEffectiveLevel() == logging.INFO

    logger.info('bar')
    capture = capsys.readouterr()
    lines = capture.out.splitlines()
    assert 1 == len(lines)
    assert '[INFO] [some-proc]: bar' == lines[0]
    assert 0 == len(capture.err)


def test_log_default_format(log_dir):
    """Test logging to the main log file when using the default logs format."""
    launch.logging.reset()
    launch.logging.launch_config.level = logging.WARN
    launch.logging.launch_config.log_dir = log_dir
    logger = launch.logging.get_logger('some-proc')
    logger.addHandler(launch.logging.launch_config.get_log_file_handler())
    assert logger.getEffectiveLevel() == logging.WARN

    logger.error('baz')

    launch.logging.launch_config.get_log_file_handler().flush()
    assert os.path.exists(launch.logging.launch_config.get_log_file_path())
    assert 0 != os.stat(launch.logging.launch_config.get_log_file_path()).st_size

    with open(launch.logging.launch_config.get_log_file_path(), 'r') as f:
        lines = f.readlines()
        assert 1 == len(lines)
        assert re.match(r'[0-9]+\.[0-9]+ \[ERROR\] \[some-proc\]: baz', lines[0]) is not None


def test_logging_env_var_format(capsys, monkeypatch):
    monkeypatch.setenv('OVERRIDE_LAUNCH_SCREEN_FORMAT', 'TESTSCREEN {message} {name} TESTSCREEN')
    monkeypatch.setenv('OVERRIDE_LAUNCH_LOG_FORMAT', 'TESTLOG {message} {name} TESTLOG')
    launch.logging.reset()

    logger = launch.logging.get_logger('some-proc')
    logger.addHandler(launch.logging.launch_config.get_screen_handler())

    logger.info('bar')
    capture = capsys.readouterr()
    lines = capture.out.splitlines()
    assert 'TESTSCREEN bar some-proc TESTSCREEN' == lines.pop()

    launch.logging.launch_config.get_log_file_handler().flush()
    with open(launch.logging.launch_config.get_log_file_path(), 'r') as f:
        lines = f.readlines()
        assert 'TESTLOG bar some-proc TESTLOG\n' == lines[0]


def test_log_handler_factory(log_dir):
    """Test logging using a custom log handlers."""
    class TestStreamHandler(launch.logging.handlers.Handler):

        def __init__(self, output):
            super().__init__()
            self._output = output

        def emit(self, record):
            self._output.append(self.format(record))

    import collections
    outputs = collections.defaultdict(list)

    launch.logging.reset()
    launch.logging.launch_config.level = logging.WARN
    launch.logging.launch_config.log_dir = log_dir
    launch.logging.launch_config.log_handler_factory = (
        lambda path, encoding=None: TestStreamHandler(
            output=outputs[path]
        )
    )

    logger = launch.logging.get_logger('some-proc')
    logger.addHandler(launch.logging.launch_config.get_log_file_handler())

    logger.debug('foo')
    logger.error('baz')

    path = launch.logging.launch_config.get_log_file_path()
    assert path in outputs
    assert len(outputs[path]) == 1
    assert outputs[path][0].endswith('baz')


def fake_make_unique_log_dir(*, base_path):
    # Passthrough; do not create the directory
    return base_path


def fake_renew_latest_log_dir(*, log_dir):
    # Passthrough; do not create the symlink
    return True


@mock.patch('launch.logging._make_unique_log_dir', mock.MagicMock(wraps=fake_make_unique_log_dir))
@mock.patch(
    'launch.logging._renew_latest_log_dir',
    mock.MagicMock(wraps=fake_renew_latest_log_dir)
)
def test_get_logging_directory():
    launch.logging.launch_config.reset()
    os.environ.pop('ROS_LOG_DIR', None)
    os.environ.pop('ROS_HOME', None)
    home = pathlib.Path.home()
    assert str(home)

    # Default case without ROS_LOG_DIR or ROS_HOME being set (but with HOME)
    default_dir = str(home / '.ros/log')
    # This ensures that the launch config will check the environment again
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == default_dir

    # Use $ROS_LOG_DIR if it is set
    my_log_dir_raw = '/my/ros_log_dir'
    my_log_dir = str(pathlib.Path(my_log_dir_raw))
    os.environ['ROS_LOG_DIR'] = my_log_dir
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == my_log_dir
    # Make sure it converts path separators when necessary
    os.environ['ROS_LOG_DIR'] = my_log_dir_raw
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == my_log_dir
    # Setting ROS_HOME won't change anything since ROS_LOG_DIR is used first
    os.environ['ROS_HOME'] = '/this/wont/be/used'
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == my_log_dir
    os.environ.pop('ROS_HOME', None)
    # Empty is considered unset
    os.environ['ROS_LOG_DIR'] = ''
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == default_dir
    # Make sure '~' is expanded to the home directory
    os.environ['ROS_LOG_DIR'] = '~/logdir'
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == str(home / 'logdir')

    os.environ.pop('ROS_LOG_DIR', None)

    # Without ROS_LOG_DIR, use $ROS_HOME/log
    fake_ros_home = home / '.fakeroshome'
    fake_ros_home_log_dir = str(fake_ros_home / 'log')
    os.environ['ROS_HOME'] = str(fake_ros_home)
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == fake_ros_home_log_dir
    # Make sure it converts path separators when necessary
    my_ros_home_raw = '/my/ros/home'
    my_ros_home_log_dir = str(pathlib.Path(my_ros_home_raw) / 'log')
    os.environ['ROS_HOME'] = my_ros_home_raw
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == my_ros_home_log_dir
    # Empty is considered unset
    os.environ['ROS_HOME'] = ''
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == default_dir
    # Make sure '~' is expanded to the home directory
    os.environ['ROS_HOME'] = '~/.fakeroshome'
    launch.logging.launch_config.log_dir = None
    assert launch.logging.launch_config.log_dir == fake_ros_home_log_dir

    os.environ.pop('ROS_HOME', None)
    launch.logging.launch_config.reset()
