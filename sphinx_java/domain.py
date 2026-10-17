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

import re
from collections.abc import Callable, Iterator, Set
from itertools import accumulate
from typing import Any, ClassVar, cast

from docutils import nodes
from docutils.nodes import Element, Node
from docutils.parsers.rst import directives
from sphinx import addnodes
from sphinx.addnodes import desc_signature, pending_xref
from sphinx.application import Sphinx
from sphinx.builders import Builder
from sphinx.config import Config
from sphinx.directives import ObjectDescription
from sphinx.domains import Domain, ObjType
from sphinx.environment import BuildEnvironment
from sphinx.locale import _, __
from sphinx.roles import XRefRole
from sphinx.util import logging
from sphinx.util.docfields import Field, GroupedField, TypedField
from sphinx.util.docutils import SphinxDirective
from sphinx.util.nodes import make_refnode
from sphinx.util.typing import OptionSpec

from . import _javalang as javalang
from . import extdoc, formatter
from .javase import JAVA_LANG_TYPES

logger = logging.getLogger(__name__)

# The change in bracket depth at each bracket token
BRACKET_DEPTHS = {'(': 1, '[': 1, '{': 1, ')': -1, ']': -1, '}': -1}

PRIMITIVE_TYPES = frozenset({'boolean', 'byte', 'char', 'short', 'int', 'long', 'float', 'double', 'void'})


class JavaObject(ObjectDescription[str]):
    # The type parameters that the signature declares
    own_type_params: frozenset[str] = frozenset()
    # The arguments of each annotation in the signature, by position
    annotation_args: dict[Any, str]
    # The positions of the annotations written after a modifier
    annotations_after_modifiers: set[Any]

    option_spec: ClassVar[OptionSpec] = {
        **ObjectDescription.option_spec,
        'package': directives.unchanged,
        'outertype': directives.unchanged,
    }

    def _build_ref_node(self, target: str) -> pending_xref:
        ref = addnodes.pending_xref('', refdomain='java', reftype='type', reftarget=target, modname=None,
                                    classname=None)
        ref['java:outertype'] = self.get_type()

        package = _import_qualifier(self.env, target)

        if package:
            ref['java:imported'] = True
            ref['java:package'] = package
        else:
            ref['java:imported'] = False
            ref['java:package'] = self.get_package()

        return ref

    def _parse(self, parse: Callable[[str], Any], sig: str) -> Any:
        try:
            member = parse(sig)
        # The parser raises StopIteration for a signature that ends early
        except (javalang.parser.JavaSyntaxError, javalang.tokenizer.LexerError, StopIteration):
            lname = self.env.get_domain('java').object_types[self.objtype].lname
            raise self.error(f'syntax error in {lname} signature') from None
        self.annotation_args, self.annotations_after_modifiers = _annotations(sig)
        return member

    def _type_params(self) -> set[str]:
        """ The names of the type parameters in scope """
        return _type_params_in_scope(self.env) | self.own_type_params

    def _build_annotations(self, annotations: list[Any] | None) -> list[Node]:
        """ The annotations, each followed by a space """
        parts: list[Node] = []
        for annotation in annotations or []:
            parts.append(nodes.Text('@'))
            parts += self._build_type_node(_reference_type(annotation.name))
            parts.append(nodes.Text(self.annotation_args.get(annotation.position, '') + ' '))
        return parts

    def _build_dimensions(self, dimensions: list[Any] | None) -> list[Node]:
        """ The array dimensions, each with its list of annotations or None """
        parts: list[Node] = []
        for annotations in dimensions or []:
            if annotations:
                parts.append(nodes.Text(' '))
                parts += self._build_annotations(annotations)
            parts.append(nodes.Text('[]'))
        return parts

    def _build_type_node(self, typ: Any) -> list[Node]:
        if typ is None:
            return [nodes.Text('void')]

        annotations = self._build_annotations(typ.annotations)
        dims = self._build_dimensions(typ.dimensions)
        if not isinstance(typ, javalang.tree.ReferenceType) or (
                not typ.sub_type and not typ.arguments and typ.name in self._type_params()):
            return [*annotations, nodes.Text(typ.name), *dims]

        parts: list[Node] = []

        # The package of a qualified name, as one reference
        package = []
        while typ.sub_type and not typ.arguments and typ.name[0].islower():
            package.append(typ.name)
            typ = typ.sub_type
        if package:
            target = '.'.join(package)
            ref_node = self._build_ref_node(target)
            ref_node['reftype'] = 'package'
            ref_node['java:nowarn'] = True
            ref_node += nodes.Text(target)
            parts += [ref_node, nodes.Text('.')]
            target += '.' + typ.name
        else:
            target = typ.name

        while typ:
            parts += self._build_annotations(typ.annotations)
            ref_node = self._build_ref_node(target)
            ref_node += nodes.Text(typ.name)
            parts.append(ref_node)

            if typ.arguments:
                parts += self._build_type_args(typ.arguments)

            typ = typ.sub_type

            if typ:
                target = target + '.' + typ.name
                parts.append(nodes.Text('.'))

        return parts + dims

    def _build_type_args(self, type_args: list[Any]) -> list[Node]:
        parts: list[Node] = [nodes.Text('<')]
        for i, type_arg in enumerate(type_args):
            if i > 0:
                parts.append(nodes.Text(', '))

            parts += self._build_annotations(type_arg.annotations)
            if type_arg.pattern_type == '?':
                parts.append(nodes.Text('?'))
            else:
                if type_arg.pattern_type:
                    parts.append(nodes.Text(f'? {type_arg.pattern_type} '))
                parts.extend(self._build_type_node(type_arg.type))
        parts.append(nodes.Text('>'))
        return parts

    def _build_type_node_list(self, types: list[Any]) -> list[Node]:
        parts = self._build_type_node(types[0])
        for typ in types[1:]:
            parts.append(nodes.Text(', '))
            parts.extend(self._build_type_node(typ))
        return parts

    def _build_type_params(self, type_params: list[Any]) -> list[Node]:
        parts: list[Node] = [nodes.Text('<')]
        for i, type_param in enumerate(type_params):
            if i > 0:
                parts.append(nodes.Text(', '))
            parts += self._build_annotations(type_param.annotations)
            parts.append(nodes.Text(type_param.name))
            for j, bound in enumerate(type_param.extends or []):
                parts.append(nodes.Text(' & ' if j else ' extends '))
                parts.extend(self._build_type_node(bound))
        parts.append(nodes.Text('>'))
        return parts

    def _build_parameter_list(self, parameters: list[Any]) -> addnodes.desc_parameterlist:
        paramlist = addnodes.desc_parameterlist()
        for parameter in parameters:
            param = addnodes.desc_parameter('', '', noemph=True)
            param += self._build_modifiers(parameter)
            param += self._build_type_node(parameter.type)

            if parameter.varargs:
                if parameter.varargs_annotations:
                    param += nodes.Text(' ')
                    param += self._build_annotations(parameter.varargs_annotations)
                param += nodes.Text('...')

            param += nodes.emphasis(' ' + parameter.name, ' ' + parameter.name)
            paramlist += param
        return paramlist

    def _add_throws(self, signode: desc_signature, throws: list[str] | None) -> None:
        if throws:
            signode += nodes.Text(' throws ')
            signode += self._build_type_node_list([_reference_type(name) for name in throws])

    def _build_modifiers(self, declaration: Any) -> list[Node]:
        """ The annotations and modifiers of a declaration, each followed by a space. An annotation written after
        a modifier, such as a type annotation on a return type, comes after the modifiers. """
        before = [a for a in declaration.annotations if a.position not in self.annotations_after_modifiers]
        after = [a for a in declaration.annotations if a.position in self.annotations_after_modifiers]
        parts = self._build_annotations(before)
        mods = formatter.output_modifiers(declaration.modifiers or set()).build()
        if mods:
            parts.append(nodes.Text(mods + ' '))
        return parts + self._build_annotations(after)

    @staticmethod
    def _overload_name(member: Any) -> str:
        """ The name of a method or constructor with its parameter types, such as foo(int, List) """
        # Receiver parameters, such as Outer.this, are left out
        param_reprs = [formatter.output_type(param.type).build() for param in member.parameters
                       if param.name.rpartition('.')[2] != 'this']
        return f'{member.name}({", ".join(param_reprs)})'

    def get_index_text(self, name: str) -> str:
        raise NotImplementedError

    def get_package(self) -> str | None:
        package: str | None = self.options.get('package', self.env.ref_context.get('java:package'))
        return package

    def get_type(self) -> str:
        outertype: str = self.options.get('outertype', '.'.join(self.env.ref_context.get('java:outertype', [])))
        return outertype

    def add_target_and_index(self, name: str, sig: str, signode: desc_signature) -> None:
        fullname = '.'.join(filter(None, (self.get_package(), self.get_type(), name)))
        basename = fullname.partition('(')[0]

        if fullname not in self.state.document.ids:
            signode['names'].append(fullname)
            signode['ids'].append(fullname)
            signode['first'] = not self.names
            self.state.document.note_explicit_target(signode)

            objects = self.env.domaindata['java']['objects']
            if fullname in objects:
                logger.warning(__('duplicate object description of %s, other instance in %s, '
                                  'use :no-index: for one of them'),
                               fullname, self.env.doc2path(objects[fullname][0]), location=signode)

            objects[fullname] = (self.env.docname, self.objtype, basename)

        self.indexnode['entries'].append(('single', self.get_index_text(name), fullname, '', None))

    def before_content(self) -> None:
        self.set_type = False

        if self.objtype == 'type' and self.names:
            self.set_type = True
            self.env.ref_context.setdefault('java:outertype', []).append(self.names[0])
        self.env.ref_context.setdefault('java:typeparams', []).append(self.own_type_params)

    def after_content(self) -> None:
        if self.set_type:
            self.env.ref_context['java:outertype'].pop()
        self.env.ref_context['java:typeparams'].pop()


class JavaMethod(JavaObject):
    doc_field_types = [
        TypedField('parameter', label=_('Parameters'),
                   names=('param', 'parameter', 'arg', 'argument'),
                   typerolename='type', typenames=('type',)),
        Field('returnvalue', label=_('Returns'), has_arg=False,
              names=('returns', 'return')),
        GroupedField('throws', names=('throws',), label=_('Throws'), rolename='type')
    ]

    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        member = self._parse(javalang.parse.parse_member_signature, sig)

        if not isinstance(member, javalang.tree.MethodDeclaration):
            raise self.error('expected method declaration')

        self.own_type_params = _type_param_names(member)
        signode += self._build_modifiers(member)

        if member.type_parameters:
            signode += self._build_type_params(member.type_parameters)
            signode += nodes.Text(' ')

        rnode = addnodes.desc_type('', '')
        rnode += self._build_type_node(member.return_type)

        signode += rnode
        signode += nodes.Text(' ')
        signode += addnodes.desc_name(member.name, member.name)
        signode += self._build_parameter_list(member.parameters)
        self._add_throws(signode, member.throws)

        # The default value of an annotation element
        if member.default is not None:
            signode += nodes.Text(' default ' + _signature_text(sig, _top_level_tokens(sig, 'default')[-1]))

        return self._overload_name(member)

    def get_index_text(self, name: str) -> str:
        return _('%s (Java method)') % name


class JavaConstructor(JavaObject):
    doc_field_types = [
        TypedField('parameter', label=_('Parameters'),
                   names=('param', 'parameter', 'arg', 'argument'),
                   typerolename='type', typenames=('type',)),
        GroupedField('throws', names=('throws',), label=_('Throws'), rolename='type')
    ]

    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        member = self._parse(javalang.parse.parse_constructor_signature, sig)

        if not isinstance(member, javalang.tree.ConstructorDeclaration):
            raise self.error('expected constructor declaration')
        self.own_type_params = _type_param_names(member)

        signode += self._build_modifiers(member)

        if member.type_parameters:
            signode += self._build_type_params(member.type_parameters)
            signode += nodes.Text(' ')

        signode += addnodes.desc_name(member.name, member.name)

        # A compact constructor of a record has no parameter list
        if member.parameters is None:
            name: str = member.name
            return name

        signode += self._build_parameter_list(member.parameters)
        self._add_throws(signode, member.throws)

        return self._overload_name(member)

    def get_index_text(self, name: str) -> str:
        return _('%s (Java constructor)') % name


class JavaType(JavaObject):
    doc_field_types = [
        GroupedField('parameter', names=('param',), label=_('Parameters'))
    ]

    declaration_type = ''

    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        member = self._parse(javalang.parse.parse_type_signature, sig)

        declaration_types = {
            javalang.tree.ClassDeclaration: 'class',
            javalang.tree.InterfaceDeclaration: 'interface',
            javalang.tree.EnumDeclaration: 'enum',
            javalang.tree.AnnotationDeclaration: 'annotation',
            javalang.tree.RecordDeclaration: 'record',
        }
        self.declaration_type = declaration_types[type(member)]
        self.own_type_params = _type_param_names(member)

        signode += self._build_modifiers(member)

        keyword = '@interface' if self.declaration_type == 'annotation' else self.declaration_type
        signode += nodes.Text(keyword + ' ')

        signode += addnodes.desc_name(member.name, member.name)

        if self.declaration_type in ('class', 'interface', 'record') and member.type_parameters:
            signode += self._build_type_params(member.type_parameters)

        if self.declaration_type == 'record':
            signode += self._build_parameter_list(member.parameters)

        if self.declaration_type == 'class':
            if member.extends:
                signode += nodes.Text(' extends ')
                signode += self._build_type_node(member.extends)
            if member.implements:
                signode += nodes.Text(' implements ')
                signode += self._build_type_node_list(member.implements)
        elif self.declaration_type == 'interface':
            if member.extends:
                signode += nodes.Text(' extends ')
                signode += self._build_type_node_list(member.extends)
        elif self.declaration_type in ('enum', 'record'):
            if member.implements:
                signode += nodes.Text(' implements ')
                signode += self._build_type_node_list(member.implements)

        if self.declaration_type in ('class', 'interface') and member.permits:
            signode += nodes.Text(' permits ')
            signode += self._build_type_node_list(member.permits)

        name: str = member.name
        return name

    def get_index_text(self, name: str) -> str:
        return _('%s (Java %s)') % (name, self.declaration_type)


class JavaField(JavaObject):
    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        member = self._parse(javalang.parse.parse_member_signature, sig)

        if not isinstance(member, javalang.tree.FieldDeclaration):
            raise self.error('expected field declaration')

        signode += self._build_modifiers(member)

        tnode = addnodes.desc_type('', '')
        tnode += self._build_type_node(member.type)

        signode += tnode
        signode += nodes.Text(' ')

        if len(member.declarators) > 1:
            raise self.error('only one field may be documented at a time')

        declarator = member.declarators[0]
        signode += addnodes.desc_name(declarator.name, declarator.name)

        dim = '[]' * len(declarator.dimensions)
        signode += nodes.Text(dim)

        if declarator.initializer:
            signode += nodes.Text(' = ' + _initializer(sig))

        name: str = declarator.name
        return name

    def get_index_text(self, name: str) -> str:
        return _('%s (Java field)') % name


class JavaEnumConstant(JavaObject):
    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        constant = self._parse(_parse_enum_constant, sig)
        signode += self._build_modifiers(constant)
        signode += addnodes.desc_name(constant.name, constant.name)
        if constant.arguments is not None:
            signode += nodes.Text(_enum_constant_args(sig))
        name: str = constant.name
        return name

    def get_index_text(self, name: str) -> str:
        return _('%s (Java enum constant)') % name


class JavaPackage(SphinxDirective):
    """ Sets the current package, and adds a target and an index entry for it """

    has_content = False
    required_arguments = 1
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec: ClassVar[OptionSpec] = {
        'no-index': directives.flag,
        'noindex': directives.flag,
    }

    def run(self) -> list[Node]:
        package = self.arguments[0].strip()
        noindex = 'no-index' in self.options or 'noindex' in self.options
        self.env.ref_context['java:package'] = package
        ret: list[Node] = []

        if not noindex:
            cast('JavaDomain', self.env.get_domain('java')).note_package(package, self.env.docname)
            targetnode = nodes.target('', '', ids=['package-' + package], ismod=True)
            self.state.document.note_explicit_target(targetnode)
            ret.append(targetnode)

            indextext = _('%s (package)') % package
            ret.append(addnodes.index(entries=[('single', indextext, 'package-' + package, '', None)]))

        return ret


class JavaImport(SphinxDirective):
    """ Declares the package of a type, for resolving references to it """

    has_content = False
    required_arguments = 2
    optional_arguments = 0
    final_argument_whitespace = False

    def run(self) -> list[Node]:
        package, typename = self.arguments
        imports = self.env.ref_context.setdefault('java:imports', {})
        imports[typename] = package
        # A nested type, such as Map.Entry, is also imported by its simple name
        outer, _, name = typename.rpartition('.')
        if outer:
            imports[name] = package + '.' + outer
        return []


def _annotations(sig: str) -> tuple[dict[Any, str], set[Any]]:
    """ The arguments of each annotation in a signature as written, such as ("unchecked"), by the position of its
    @, and the positions of the annotations written after a modifier """
    tokens = list(javalang.tokenizer.tokenize(sig))
    args = {}
    after_modifier = set()
    # The index of the @ of each annotation, by the index of its last token
    starts: dict[int, int] = {}
    for i, token in enumerate(tokens):
        if token.value != '@' or tokens[i + 1].value == 'interface':
            continue
        # Skip the qualified name
        last = i + 1
        while tokens[last + 1].value == '.':
            last += 2
        if tokens[last + 1].value == '(':
            paren = tokens[last + 1]
            depths = accumulate(BRACKET_DEPTHS.get(t.value, 0) for t in tokens[last + 1:])
            last += 1 + next(j for j, depth in enumerate(depths) if not depth)
            args[token.position] = sig[paren.position.column - 1:tokens[last].position.column]
        starts[last] = i

        # The token before this annotation and any annotations just before it
        before = i - 1
        while before in starts:
            before = starts[before] - 1
        modifier = before >= 0 and (isinstance(tokens[before], javalang.tokenizer.Modifier)
                                    or tokens[before].value == 'sealed')
        if modifier:
            after_modifier.add(token.position)
    return args, after_modifier


def _parse_enum_constant(sig: str) -> Any:
    parser = javalang.parser.Parser(javalang.tokenizer.tokenize(sig))
    constant = parser.parse_enum_constant()
    if not parser.would_accept(javalang.tokenizer.EndOfInput):
        parser.illegal('Expected end of signature')
    return constant


def _top_level_tokens(sig: str, value: str) -> list[Any]:
    """ The tokens of a signature with a value, such as =, outside brackets """
    tokens = list(javalang.tokenizer.tokenize(sig))
    depths = accumulate((BRACKET_DEPTHS.get(token.value, 0) for token in tokens), initial=0)
    return [token for token, depth in zip(tokens, depths, strict=False) if token.value == value and not depth]


def _signature_text(sig: str, token: Any, after: bool = True) -> str:
    """ The signature text after a token, or from it, as written without a trailing ; """
    # Columns start at 1, and a signature is one line
    start = token.position.column - 1 + (len(token.value) if after else 0)
    return sig[start:].strip().removesuffix(';').rstrip()


def _enum_constant_args(sig: str) -> str:
    """ The arguments of an enum constant signature as written, from the last ( outside brackets """
    return _signature_text(sig, _top_level_tokens(sig, '(')[-1], after=False)


def _initializer(sig: str) -> str:
    """ The initializer of a field signature as written, such as 1 << 3 """
    return _signature_text(sig, _top_level_tokens(sig, '=')[0])


def _reference_type(name: str) -> Any:
    """ The syntax tree node for a qualified type name, such as java.io.IOException """
    typ = None
    for part in reversed(name.split('.')):
        typ = javalang.tree.ReferenceType(name=part, sub_type=typ)
    return typ


def _import_qualifier(env: BuildEnvironment, target: str) -> str | None:
    """ The package, or package and outer types, that qualify a type name through an import or java.lang """
    imports = env.ref_context.get('java:imports', {})
    first = target.partition('.')[0]
    qualifier: str | None = imports.get(target) or imports.get(first)
    if not qualifier and first in JAVA_LANG_TYPES:
        qualifier = 'java.lang'
    return qualifier


def _type_param_names(member: Any) -> frozenset[str]:
    return frozenset(param.name for param in getattr(member, 'type_parameters', None) or [])


def _type_params_in_scope(env: BuildEnvironment) -> set[str]:
    """ The type parameters of the enclosing types and members """
    return {name for names in env.ref_context.get('java:typeparams', []) for name in names}


def _note_context(env: BuildEnvironment, refnode: Element, target: str) -> None:
    """ Store the current type and package on a reference, for resolving it, or mark it as plain text """
    refnode['java:outertype'] = '.'.join(env.ref_context.get('java:outertype', []))

    # Strip a method component from the target
    basetype = target
    if '(' in basetype:
        basetype = basetype.partition('(')[0]
        if '.' in basetype:
            basetype = basetype.rpartition('.')[0]

    package = _import_qualifier(env, basetype)

    if package:
        refnode['java:imported'] = True
        refnode['java:package'] = package
    else:
        refnode['java:imported'] = False
        refnode['java:package'] = env.ref_context.get('java:package')

    # A primitive type or a type parameter, which has no target
    base = target.removesuffix('...').rstrip('[]')
    if base in PRIMITIVE_TYPES or base in _type_params_in_scope(env):
        refnode['java:plain'] = True


class JavaXRefRole(XRefRole):
    # An explicit title needs a space before the target, so that a generic type is a target
    explicit_title_re = re.compile(r'^(.+?)\s+(?<!\x00)<(.*?)>$', re.DOTALL)

    def process_link(self, env: BuildEnvironment, refnode: Element, has_explicit_title: bool, title: str,
                     target: str) -> tuple[str, str]:
        # The type without its type arguments, such as java.util.List for java.util.List<String>
        target = re.sub(r'<.*>', '', target.lstrip('~'))
        _note_context(env, refnode, target)

        # A leading tilde shows only the last component of the name
        if not has_explicit_title and title[0:1] == '~':
            title = re.sub(r'<.*>', '', title.partition('(')[0])
            title = title[1:]
            dot = title.rfind('.')
            if dot != -1:
                title = title[dot + 1:]

        return title, target


class JavaDomain(Domain):
    """ Java language domain """

    name = 'java'
    label = 'Java'

    object_types = {
        'package': ObjType(_('package'), 'package', 'ref'),
        'type': ObjType(_('type'), 'type', 'ref'),
        'field': ObjType(_('field'), 'field', 'ref'),
        'enumconstant': ObjType(_('enum constant'), 'field', 'ref'),
        'constructor': ObjType(_('constructor'), 'construct', 'ref'),
        'method': ObjType(_('method'), 'meth', 'ref')
    }

    directives = {
        'package': JavaPackage,
        'type': JavaType,
        'field': JavaField,
        'enumconstant': JavaEnumConstant,
        'constructor': JavaConstructor,
        'method': JavaMethod,
        'import': JavaImport
    }

    roles = {
        'package': JavaXRefRole(),
        'type': JavaXRefRole(),
        'field': JavaXRefRole(),
        'construct': JavaXRefRole(),
        'meth': JavaXRefRole(),
        'ref': JavaXRefRole(),
    }

    # Fullname to docname, object type and basename
    initial_data: ClassVar[dict[str, dict[str, tuple[str, str, str]]]] = {
        'objects': {},
    }

    @property
    def objects(self) -> dict[str, tuple[str, str, str]]:
        objects: dict[str, tuple[str, str, str]] = self.data['objects']
        return objects

    def note_package(self, package: str, docname: str) -> None:
        """ Record the page that documents a package. Of several pages, the first by name is used. """
        existing = self.objects.get(package)
        if existing is None or existing[1] != 'package' or docname < existing[0]:
            self.objects[package] = (docname, 'package', package)

    def clear_doc(self, docname: str) -> None:
        for fullname, (fn, _objtype, _basename) in list(self.objects.items()):
            if fn == docname:
                del self.objects[fullname]

    def merge_domaindata(self, docnames: Set[str], otherdata: dict[str, Any]) -> None:
        for fullname, data in otherdata['objects'].items():
            if data[0] not in docnames:
                continue
            if data[1] == 'package':
                self.note_package(fullname, data[0])
            else:
                self.objects[fullname] = data

    def process_field_xref(self, pnode: pending_xref) -> None:
        _note_context(self.env, pnode, pnode['reftarget'])

    def find_object(self, target: str, node: pending_xref) -> str | None:
        """ The full name of the object that a reference points to """
        objects = self.objects
        package = node.get('java:package')
        type_context = node.get('java:outertype')

        candidates = [target]
        if package:
            candidates.append(package + '.' + target)
            if type_context:
                candidates.append(package + '.' + type_context + '.' + target)
        for fullname in candidates:
            if fullname in objects:
                return fullname

        # A matching suffix, or failing that the last object with a matching basename
        suffix = '.' + target
        basename_suffix = suffix.partition('(')[0]
        basename_match = None
        for fullname, (_docname, _objtype, basename) in objects.items():
            if fullname.endswith(suffix):
                return fullname
            if basename.endswith(basename_suffix):
                basename_match = fullname
        return basename_match

    def external_ref(self, config: Config, target: str, node: pending_xref) -> nodes.reference | None:
        """ A reference to the external docs for a target """
        candidates = [target]
        if target.partition('.')[0] in JAVA_LANG_TYPES:
            candidates.append('java.lang.' + target)
        if node.get('java:imported'):
            candidates.append(node['java:package'] + '.' + target)
        for fulltarget in candidates:
            ref = extdoc.get_javadoc_ref(config, fulltarget, fulltarget)
            if ref:
                return ref
        return None

    def resolve_xref(self, env: BuildEnvironment, fromdocname: str, builder: Builder, typ: str, target: str,
                     node: pending_xref, contnode: Element) -> nodes.reference | None:
        if node.get('java:plain'):
            return None
        fullname = self.find_object(target, node)
        if fullname:
            docname, objtype, _basename = self.objects[fullname]
            return make_refnode(builder, fromdocname, docname, _anchor(fullname, objtype), contnode, fullname)

        ref = self.external_ref(env.config, target, node)
        if ref:
            ref.append(contnode)
        return ref

    def resolve_any_xref(self, env: BuildEnvironment, fromdocname: str, builder: Builder, target: str,
                         node: pending_xref, contnode: Element) -> list[tuple[str, nodes.reference]]:
        ref = self.resolve_xref(env, fromdocname, builder, 'ref', target, node, contnode)
        if ref is None:
            return []
        fullname = self.find_object(target, node)
        role = self.role_for_objtype(self.objects[fullname][1]) if fullname else 'type'
        return [(f'java:{role}', ref)]

    def get_objects(self) -> Iterator[tuple[str, str, str, str, str, int]]:
        for refname, (docname, objtype, _basename) in self.objects.items():
            yield refname, refname, objtype, docname, _anchor(refname, objtype), 1


def suppress_missing_reference(app: Sphinx, domain: Domain, node: pending_xref) -> bool:
    """ Whether to leave out the warning for a reference that is plain text by design, or optional """
    return bool(node.get('java:plain') or node.get('java:nowarn'))


def _anchor(fullname: str, objtype: str) -> str:
    """ The id of an object's target """
    return 'package-' + fullname if objtype == 'package' else fullname
