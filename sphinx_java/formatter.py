#
# Copyright 2012-2015 Bronto Software, Inc. and contributors
# Modifications copyright 2026 djungelorm
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
#

""" Convert Java syntax tree nodes to strings """

from collections.abc import Callable, Sequence
from typing import Any, Concatenate

from . import _javalang as javalang

# The order for displaying modifiers
MODIFIERS_ORDER = ('public', 'protected', 'private', 'default', 'static', 'abstract', 'final', 'sealed',
                   'non-sealed', 'native', 'synchronized', 'transient', 'volatile', 'strictfp')


class StringBuilder(list[str]):
    def build(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return ''.join(self)


def formatter(f: Callable[Concatenate[Any, StringBuilder, ...], None]) -> Callable[..., StringBuilder]:
    """ Write to a new output, and return the output """
    def _f(node: Any, **kwargs: Any) -> StringBuilder:
        output = StringBuilder()
        f(node, output, **kwargs)
        return output

    return _f


def output_list(f: Callable[[Any, StringBuilder], object], items: Sequence[Any], output: StringBuilder,
                sep: str = ', ') -> None:
    if items:
        f(items[0], output)
        for item in items[1:]:
            output.append(sep)
            f(item, output)


@formatter
def output_type(typ: Any, output: StringBuilder) -> None:
    if not typ:
        output.append('void')
        return

    dim = '[]' * len(typ.dimensions) if typ.dimensions else ''

    if isinstance(typ, javalang.tree.BasicType):
        output.append(typ.name)
    else:
        while typ:
            output.append(typ.name)
            typ = typ.sub_type

            if typ:
                output.append('.')
    output.append(dim)


@formatter
def output_modifiers(modifiers: Any, output: StringBuilder) -> None:
    ordered_modifiers = [mod for mod in MODIFIERS_ORDER if mod in modifiers]
    output_list(lambda mod, output: output.append(mod), ordered_modifiers, output, ' ')
