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

"""Module for parsing substitutions."""

import os
import re
from typing import Text

from ament_index_python.packages import get_package_share_directory

from .expose import instantiate_substitution
from ..substitutions import TextSubstitution
from ..utilities.type_utils import NormalizedValueType
from ..utilities.type_utils import StrSomeValueType


def replace_escaped_characters(data: Text) -> Text:
    """Search escaped characters and replace them."""
    return re.sub(r'\\(.)', r'\1', data)


def _make_extract_substitution():
    from lark import Token
    from lark import Transformer

    class ExtractSubstitution(Transformer):
        """Extract a substitution."""

        def part(self, content):
            assert len(content) == 1
            content = content[0]
            if isinstance(content, Token):
                assert content.type.endswith('_RSTRING')
                return TextSubstitution(text=replace_escaped_characters(content.value))
            return content

        single_quoted_part = part
        double_quoted_part = part

        def value(self, parts):
            if len(parts) == 1 and isinstance(parts[0], list):
                # Deal with single and double quoted templates
                return parts[0]
            return parts

        single_quoted_value = value
        double_quoted_value = value

        def arguments(self, values):
            if len(values) > 1:
                # Deal with tail recursive argument parsing
                return [*values[0], values[1]]
            return values

        single_quoted_arguments = arguments
        double_quoted_arguments = arguments

        def substitution(self, args):
            assert len(args) >= 1
            name = args[0]
            assert isinstance(name, Token)
            assert name.type == 'IDENTIFIER'
            return instantiate_substitution(name.value, *args[1:])

        single_quoted_substitution = substitution
        double_quoted_substitution = substitution

        def fragment(self, content):
            assert len(content) == 1
            content = content[0]
            if isinstance(content, Token):
                assert content.type.endswith('_STRING')
                return TextSubstitution(text=replace_escaped_characters(content.value))
            return content

        single_quoted_fragment = fragment
        double_quoted_fragment = fragment

        def template(self, fragments):
            return fragments

        single_quoted_template = template
        double_quoted_template = template

    return ExtractSubstitution


def get_grammar_path():
    return os.path.join(
        get_package_share_directory('launch'), 'frontend', 'grammar.lark')


_parser = None


class _ParseError(Exception):
    pass


class _Substitution:
    __slots__ = ('name', 'arguments')

    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _SubstitutionParser:
    """
    Parse the grammar of grammar.lark without lark.

    Text is kept raw and substitutions are instantiated only after the whole string parsed,
    so errors match the Earley parser followed by ExtractSubstitution.
    """

    _identifier = re.compile(r'[a-zA-Z][a-zA-Z0-9_-]*')
    _strings = {
        '': re.compile(r'(?:[^$]|\$(?!\()|(?<=\\)\$)+'),
        "'": re.compile(r"(?:\\'|[^'\\$]|\$(?!\()|(?<=\\)\$|\\)+"),
        '"': re.compile(r'(?:\\"|[^"\\$]|\$(?!\()|(?<=\\)\$|\\)+'),
    }
    _rstrings = {
        '': re.compile(
            r"(?:\\[\"']|[^ '\\\"$()]|(?<=\\)[()]|\$(?!\()|(?<=\\)\$|\\)+"),
        "'": re.compile(
            r"(?:\\'|[^ '\\$()]|(?<=\\)[()]|\$(?!\()|(?<=\\)\$|\\)+"),
        '"': re.compile(
            r'(?:\\"|[^ "\\$()]|(?<=\\)[()]|\$(?!\()|(?<=\\)\$|\\)+'),
    }

    def __init__(self, text):
        self.text = text
        self.position = 0

    def parse(self):
        items = self._template('')
        if self.position != len(self.text):
            raise _ParseError()
        return items

    def _terminal(self, patterns, quote):
        match = patterns[quote].match(self.text, self.position)
        if match is None:
            return None
        self.position = match.end()
        return match.group()

    def _template(self, quote):
        items = []
        while self.position < len(self.text):
            text = self._terminal(self._strings, quote)
            if text is not None:
                items.append(text)
            elif self.text.startswith('$(', self.position):
                items.append(self._substitution(quote))
            else:
                break
        if quote:
            self._expect(quote)
        elif not items:
            raise _ParseError()
        return items

    def _expect(self, character):
        if not self.text.startswith(character, self.position):
            raise _ParseError()
        self.position += len(character)

    def _substitution(self, quote):
        self._expect('$(')
        name = self._identifier.match(self.text, self.position)
        if name is None:
            raise _ParseError()
        self.position = name.end()
        arguments = None
        while self.text.startswith(' ', self.position):
            self.position += 1
            if arguments is None:
                arguments = []
            arguments.append(self._value(quote))
        self._expect(')')
        return _Substitution(name.group(), arguments)

    def _value(self, quote):
        if not quote and self.text[self.position:self.position + 1] in ('"', "'"):
            nested_quote = self.text[self.position]
            self.position += 1
            return self._template(nested_quote)
        items = []
        while self.position < len(self.text):
            text = self._terminal(self._rstrings, quote)
            if text is not None:
                items.append(text)
            elif self.text.startswith('$(', self.position):
                items.append(self._substitution(quote))
            else:
                break
        if not items:
            raise _ParseError()
        return items


def _instantiate(items):
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(TextSubstitution(text=replace_escaped_characters(item)))
        elif item.arguments is None:
            result.append(instantiate_substitution(item.name))
        else:
            result.append(instantiate_substitution(
                item.name, [_instantiate(value) for value in item.arguments]))
    return result


_extract_substitution = None


def __getattr__(name):
    global _extract_substitution
    if name == 'ExtractSubstitution':
        if _extract_substitution is None:
            _extract_substitution = _make_extract_substitution()
        return _extract_substitution
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


def parse_substitution(string_value):
    global _parser
    if not string_value:
        # Grammar cannot deal with zero-width expressions.
        return [TextSubstitution(text=string_value)]
    if '$(' not in string_value:
        return [TextSubstitution(text=replace_escaped_characters(string_value))]
    try:
        return _instantiate(_SubstitutionParser(string_value).parse())
    except Exception:
        # Earley and its transformer raise the errors callers have always seen
        # (lark syntax errors, VisitError around a failed substitution).
        pass
    if _parser is None:
        from lark import Lark
        with open(get_grammar_path(), 'r') as h:
            _parser = Lark(h, start='template')
    return __getattr__('ExtractSubstitution')().transform(_parser.parse(string_value))


def parse_if_substitutions(
    value: StrSomeValueType
) -> NormalizedValueType:
    """
    Parse substitutions in `value`, if there are any, and return a normalized value type.

    If `value` is a `str`, substitutions will be interpolated in it.
    If `value` is any other scalar type, it will be returned as-is.
    If `value` is a list, the two rules above will be applied to each item.
    When interpolating substitutions in a string, `TextSubstitution` instances are resolved
    and the original `str` is left.

    :raise: `ValueError` if the result cannot be parsed into a valid type.
    """
    data_types = set()

    def _parse_if(value):
        if isinstance(value, str):
            output = parse_substitution(value)
            if len(output) == 1 and isinstance(output[0], TextSubstitution):
                data_types.add(str)
                return output[0].text
            return output
        data_types.add(type(value))
        return value
    if isinstance(value, list):
        output = [_parse_if(x) for x in value]
    else:
        output = _parse_if(value)
    if len(data_types) > 1:
        raise ValueError('The result is a non-uniform list')
    return output
