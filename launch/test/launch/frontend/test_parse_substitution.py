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

"""Compare the recursive-descent substitution parser with Earley."""

from lark import Lark
import launch.frontend.parse_substitution as ps
from launch.substitution import Substitution

import pytest


CASES = (
    '', 'a', "'a'", '"a"', '$', '$ (a)', 'a$b', '\\$', '\\a', 'a\\\nb',
    'a\\\\b', '(a)', '\\(a\\)', '$(var a)', '$(var a)$(var b)',
    'prefix$(var a)suffix', '$(dirname)', '$(env X fallback)', '$(env X "")',
    "$(env X '')", '$(var "a b")', "$(var 'a b')", '$(env X $(var a))',
    '$(var a$(env X b)c)', '$(var "$(env X a) suffix")',
    "$(var '$(env X a) suffix')", '$(var "$(env X a$(var b))")',
    "$(var '$(env X a$(var b))')", '$(var "$(env X \'a\')")',
    '$(var \'$(env X "a")\')', '$(var a\\ b)', '$(env a\\ $(var b))',
    '$(var a\\))', '$(var a\\\\))', '$(var a\\\\\\))', '$(var \\(a\\))',
    'a\\$(var b)', 'a\\\\$(var b)', '$(var "a\\"b")', "$(var 'a\\'b')",
    '$(var "a\\\\"b")', "$(var 'a\\\\'b')", '$(var "a\\\nb")',
    '$(var \t)', '$(var \n)', '$(eval "ceil(1.3)")',
    '$(var)', '$(unknown a)', '$(a-b_1 a)', '$(var "")', "$(var '')",
    '$(', '$(var', '$(var )', '$(var  a)', '$(var a )', '$(env X  b)',
    '$(var\ta)', '$(var\na)', '$(1 a)', '$(_a a)', '$(é a)',
    '$(var "a"b)', "$(var 'a'b)", '$(var a\\)', '$(var "a\\")',
    '$(var \\$(var a))', '$(var a(b))', '$(var a\\$(var b))',
)


def _rep(value, ancestors=()):
    if id(value) in ancestors:
        return ('reference', ancestors.index(id(value)))
    ancestors = (*ancestors, id(value))
    if isinstance(value, list):
        return [_rep(item, ancestors) for item in value]
    if isinstance(value, tuple):
        return tuple(_rep(item, ancestors) for item in value)
    if isinstance(value, Substitution):
        return type(value), {key: _rep(item, ancestors) for key, item in vars(value).items()}
    return value


@pytest.fixture(scope='module')
def earley():
    """Construct the original parser as the equivalence reference."""
    with open(ps.get_grammar_path()) as stream:
        return Lark(stream, start='template')


@pytest.mark.parametrize('text', CASES)
def test_earley_equivalence(earley, text):
    """Preserve grammar trees, transformed objects and exception messages."""
    if not text:
        assert _rep(ps.parse_substitution(text)) == _rep([ps.TextSubstitution(text='')])
        return
    try:
        tree = earley.parse(text)
    except Exception as parse_error:
        with pytest.raises(type(parse_error)) as actual:
            ps.parse_substitution(text)
        assert str(actual.value) == str(parse_error)
        return
    assert ps._SubstitutionParser(text).parse() == tree
    try:
        expected = ps.ExtractSubstitution().transform(tree)
    except Exception as expected_error:
        with pytest.raises(type(expected_error)) as actual:
            ps.parse_substitution(text)
        assert str(actual.value) == str(expected_error)
    else:
        assert _rep(ps.parse_substitution(text)) == _rep(expected)


def test_valid_inputs_do_not_construct_earley(monkeypatch):
    """Keep Earley construction off both successful parsing paths."""
    def unexpected_parser(*args, **kwargs):
        pytest.fail('Earley must only be constructed after a syntax rejection')

    monkeypatch.setattr(ps, '_parser', None)
    monkeypatch.setattr(ps, 'Lark', unexpected_parser)
    for text in ('', 'a\\b', '$(var a)', '$(env X "")', 'a\\$(var b)'):
        ps.parse_substitution(text)
    assert ps._parser is None


def test_invalid_inputs_construct_earley_once(monkeypatch):
    """Reuse the lazy Earley parser for original syntax diagnostics."""
    constructed = []

    def construct_parser(*args, **kwargs):
        parser = Lark(*args, **kwargs)
        constructed.append(parser)
        return parser

    monkeypatch.setattr(ps, '_parser', None)
    monkeypatch.setattr(ps, 'Lark', construct_parser)
    for text in ('$(', '$(var )'):
        with pytest.raises(ps._ParseError):
            ps._SubstitutionParser(text).parse()
        with pytest.raises(Exception) as error:
            ps.parse_substitution(text)
        assert not isinstance(error.value, ps._ParseError)
    assert len(constructed) == 1
    assert ps._parser is constructed[0]
