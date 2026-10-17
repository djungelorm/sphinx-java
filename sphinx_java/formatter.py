#
# Copyright 2012-2015 Bronto Software, Inc. and contributors
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
MODIFIERS_ORDER = ('public', 'protected', 'private', 'static', 'abstract', 'final',
                   'native', 'synchronized', 'transient', 'volatile', 'strictfp')


class StringBuilder(list[str]):
    def build(self) -> str:
        return str(self)

    def __str__(self) -> str:
        return ''.join(self)


def formatter(f: Callable[Concatenate[Any, StringBuilder, ...], None]) -> Callable[..., StringBuilder]:
    """ Make the output argument optional, and return the output """
    def _f(node: Any, output: StringBuilder | None = None, **kwargs: Any) -> StringBuilder:
        if output is None:
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
def output_type(typ: Any, output: StringBuilder, with_generics: bool = True) -> None:
    if not typ:
        output.append('void')
        return

    dim = '[]' * len(typ.dimensions) if typ.dimensions else ''

    if isinstance(typ, javalang.tree.BasicType):
        output.append(typ.name)
    else:
        while typ:
            output.append(typ.name)

            if with_generics:
                output_type_args(typ.arguments, output)

            typ = typ.sub_type

            if typ:
                output.append('.')
    output.append(dim)


@formatter
def output_type_arg(type_arg: Any, output: StringBuilder) -> None:
    if type_arg.pattern_type == '?':
        output.append('?')
    else:
        if type_arg.pattern_type:
            output.append('? ')
            output.append(type_arg.pattern_type)
            output.append(' ')

        output_type(type_arg.type, output)


@formatter
def output_type_args(type_args: Any, output: StringBuilder) -> None:
    if type_args:
        output.append('<')
        output_list(output_type_arg, type_args, output, ', ')
        output.append('>')


@formatter
def output_type_param(type_param: Any, output: StringBuilder) -> None:
    output.append(type_param.name)

    if type_param.extends:
        output.append(' extends ')
        output_list(output_type, type_param.extends, output, ' & ')


@formatter
def output_type_params(type_params: Any, output: StringBuilder) -> None:
    output.append('<')
    output_list(output_type_param, type_params, output, ', ')
    output.append('>')


@formatter
def output_modifiers(modifiers: Any, output: StringBuilder) -> None:
    ordered_modifiers = [mod for mod in MODIFIERS_ORDER if mod in modifiers]
    output_list(lambda mod, output: output.append(mod), ordered_modifiers, output, ' ')
