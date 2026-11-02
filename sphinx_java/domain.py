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
from collections.abc import Iterator, Set
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

from . import extdoc, syntax
from .javase import JAVA_LANG_TYPES
from .syntax import Annotation, Declaration, JavaSyntaxError, Modifiers, Parameter, Type, TypeArgument, TypeParameter

logger = logging.getLogger(__name__)

# The order for displaying modifiers, from the Java Language Specification
MODIFIERS_ORDER = ('public', 'protected', 'private', 'abstract', 'default', 'static', 'final', 'sealed',
                   'non-sealed', 'transient', 'volatile', 'synchronized', 'native', 'strictfp')

PRIMITIVE_TYPES = frozenset({'boolean', 'byte', 'char', 'short', 'int', 'long', 'float', 'double', 'void'})


class JavaObject(ObjectDescription[str]):
    # The type parameters that the signature declares
    own_type_params: frozenset[str] = frozenset()

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

    def _parse(self, sig: str) -> Declaration:
        try:
            return syntax.parse(self.objtype, sig)
        except JavaSyntaxError:
            lname = self.env.get_domain('java').object_types[self.objtype].lname
            raise self.error(f'syntax error in {lname} signature') from None

    def _type_params(self) -> set[str]:
        """ The names of the type parameters in scope """
        return _type_params_in_scope(self.env) | self.own_type_params

    def _build_annotations(self, annotations: list[Annotation]) -> list[Node]:
        """ The annotations, each followed by a space """
        parts: list[Node] = []
        for annotation in annotations:
            parts.append(nodes.Text('@'))
            parts += self._build_type_node(Type.named(annotation.name))
            parts.append(nodes.Text(annotation.arguments + ' '))
        return parts

    def _build_dimensions(self, dimensions: list[list[Annotation]]) -> list[Node]:
        """ The array dimensions, each with its annotations """
        parts: list[Node] = []
        for annotations in dimensions:
            if annotations:
                parts.append(nodes.Text(' '))
                parts += self._build_annotations(annotations)
            parts.append(nodes.Text('[]'))
        return parts

    def _build_type_node(self, typ: Type) -> list[Node]:
        dims = self._build_dimensions(typ.dimensions)
        segments = typ.segments
        first = segments[0]
        if len(segments) == 1 and not first.arguments and (
                first.name in PRIMITIVE_TYPES or first.name in self._type_params()):
            return [*self._build_annotations(first.annotations), nodes.Text(first.name), *dims]

        parts: list[Node] = []

        # The package of a qualified name, as one reference
        package = []
        while len(segments) > 1 and not segments[0].arguments and not segments[0].annotations \
                and segments[0].name[0].islower():
            package.append(segments[0].name)
            segments = segments[1:]
        target = '.'.join(package)
        if package:
            ref_node = self._build_ref_node(target)
            ref_node['reftype'] = 'package'
            ref_node['java:nowarn'] = True
            ref_node += nodes.Text(target)
            parts += [ref_node, nodes.Text('.')]

        for i, segment in enumerate(segments):
            if i:
                parts.append(nodes.Text('.'))
            target = f'{target}.{segment.name}' if target else segment.name
            parts += self._build_annotations(segment.annotations)
            ref_node = self._build_ref_node(target)
            ref_node += nodes.Text(segment.name)
            parts.append(ref_node)
            if segment.arguments:
                parts += self._build_type_args(segment.arguments)

        return parts + dims

    def _build_type_args(self, type_args: list[TypeArgument]) -> list[Node]:
        parts: list[Node] = [nodes.Text('<')]
        for i, type_arg in enumerate(type_args):
            if i > 0:
                parts.append(nodes.Text(', '))

            parts += self._build_annotations(type_arg.annotations)
            if type_arg.wildcard:
                parts.append(nodes.Text('?' if type_arg.type is None else f'? {type_arg.wildcard} '))
            if type_arg.type is not None:
                parts.extend(self._build_type_node(type_arg.type))
        parts.append(nodes.Text('>'))
        return parts

    def _build_type_node_list(self, types: list[Type]) -> list[Node]:
        parts = self._build_type_node(types[0])
        for typ in types[1:]:
            parts.append(nodes.Text(', '))
            parts.extend(self._build_type_node(typ))
        return parts

    def _build_type_params(self, type_params: list[TypeParameter]) -> list[Node]:
        parts: list[Node] = [nodes.Text('<')]
        for i, type_param in enumerate(type_params):
            if i > 0:
                parts.append(nodes.Text(', '))
            parts += self._build_annotations(type_param.annotations)
            parts.append(nodes.Text(type_param.name))
            for j, bound in enumerate(type_param.bounds):
                parts.append(nodes.Text(' & ' if j else ' extends '))
                parts.extend(self._build_type_node(bound))
        parts.append(nodes.Text('>'))
        return parts

    def _build_parameter_list(self, parameters: list[Parameter]) -> addnodes.desc_parameterlist:
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

    def _add_throws(self, signode: desc_signature, throws: list[Type]) -> None:
        if throws:
            signode += nodes.Text(' throws ')
            signode += self._build_type_node_list(throws)

    def _build_modifiers(self, declaration: Modifiers) -> list[Node]:
        """ The annotations and modifiers of a declaration, each followed by a space. An annotation written after
        a modifier, such as a type annotation on a return type, comes after the modifiers. """
        parts = self._build_annotations(declaration.annotations)
        mods = ' '.join(mod for mod in MODIFIERS_ORDER if mod in declaration.modifiers)
        if mods:
            parts.append(nodes.Text(mods + ' '))
        return parts + self._build_annotations(declaration.annotations_after_modifiers)

    @staticmethod
    def _overload_name(member: Declaration) -> str:
        """ The name of a method or constructor with its parameter types, such as foo(int, List) """
        param_reprs = ['.'.join(segment.name for segment in param.type.segments) + '[]' * len(param.type.dimensions)
                       for param in member.parameters or [] if not param.receiver]
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
        member = self._parse(sig)

        if member.kind != 'method':
            raise self.error('expected method declaration')

        self.own_type_params = _type_param_names(member)
        signode += self._build_modifiers(member)

        if member.type_parameters:
            signode += self._build_type_params(member.type_parameters)
            signode += nodes.Text(' ')

        rnode = addnodes.desc_type('', '')
        rnode += self._build_type_node(cast(Type, member.type))

        signode += rnode
        signode += nodes.Text(' ')
        signode += addnodes.desc_name(member.name, member.name)
        signode += self._build_parameter_list(member.parameters or [])
        self._add_throws(signode, member.throws)

        # The default value of an annotation element
        if member.value is not None:
            signode += nodes.Text(' default ' + member.value)

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
        member = self._parse(sig)

        if member.kind != 'constructor':
            raise self.error('expected constructor declaration')
        self.own_type_params = _type_param_names(member)

        signode += self._build_modifiers(member)

        if member.type_parameters:
            signode += self._build_type_params(member.type_parameters)
            signode += nodes.Text(' ')

        signode += addnodes.desc_name(member.name, member.name)

        # A compact constructor of a record has no parameter list
        if member.parameters is None:
            return member.name

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
        member = self._parse(sig)

        self.declaration_type = member.kind
        self.own_type_params = _type_param_names(member)

        signode += self._build_modifiers(member)

        keyword = '@interface' if self.declaration_type == 'annotation' else self.declaration_type
        signode += nodes.Text(keyword + ' ')

        signode += addnodes.desc_name(member.name, member.name)

        if member.type_parameters:
            signode += self._build_type_params(member.type_parameters)

        if member.parameters is not None:
            signode += self._build_parameter_list(member.parameters)

        for keyword, types in (('extends', member.extends), ('implements', member.implements),
                               ('permits', member.permits)):
            if types:
                signode += nodes.Text(f' {keyword} ')
                signode += self._build_type_node_list(types)

        return member.name

    def get_index_text(self, name: str) -> str:
        return _('%s (Java %s)') % (name, self.declaration_type)


class JavaField(JavaObject):
    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        member = self._parse(sig)

        if member.kind != 'field':
            raise self.error('expected field declaration')

        if member.declarators > 1:
            raise self.error('only one field may be documented at a time')

        signode += self._build_modifiers(member)

        tnode = addnodes.desc_type('', '')
        tnode += self._build_type_node(cast(Type, member.type))

        signode += tnode
        signode += nodes.Text(' ')
        signode += addnodes.desc_name(member.name, member.name)
        signode += nodes.Text('[]' * member.dimensions)

        if member.value is not None:
            signode += nodes.Text(' = ' + member.value)

        return member.name

    def get_index_text(self, name: str) -> str:
        return _('%s (Java field)') % name


class JavaEnumConstant(JavaObject):
    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        constant = self._parse(sig)
        signode += self._build_modifiers(constant)
        signode += addnodes.desc_name(constant.name, constant.name)
        if constant.value is not None:
            signode += nodes.Text(constant.value)
        return constant.name

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


def _import_qualifier(env: BuildEnvironment, target: str) -> str | None:
    """ The package, or package and outer types, that qualify a type name through an import or java.lang """
    imports = env.ref_context.get('java:imports', {})
    first = target.partition('.')[0]
    qualifier: str | None = imports.get(target) or imports.get(first)
    if not qualifier and first in JAVA_LANG_TYPES:
        qualifier = 'java.lang'
    return qualifier


def _erase_type_arguments(text: str) -> str:
    """ The text without type arguments, such as Map for Map<String, List<Integer>> """
    # Innermost type arguments first
    while (erased := re.sub(r'<[^<>]*>', '', text)) != text:
        text = erased
    return text


def _split_parameters(params: str) -> list[str]:
    """ Split a parameter list at the commas outside type arguments and annotation arguments """
    parts = []
    depth = 0
    start = 0
    for i, char in enumerate(params):
        if char in '<(':
            depth += 1
        elif char in '>)':
            depth -= 1
        elif char == ',' and depth == 0:
            parts.append(params[start:i])
            start = i + 1
    parts.append(params[start:])
    return [part for part in parts if part.strip()]


def _erase_target(target: str) -> str:
    """ The target without type arguments, with its parameter types written as in the names of methods """
    name, paren, params = target.partition('(')
    name = _erase_type_arguments(name)
    if not paren:
        return name
    # Parse the parameter types as a method signature, with a name for each parameter
    sig = ', '.join(f'{param} p{i}' for i, param in enumerate(_split_parameters(params.removesuffix(')'))))
    try:
        member = syntax.parse('method', f'void m({sig})')
    except JavaSyntaxError:
        return name + paren + _erase_type_arguments(params)
    return name + JavaObject._overload_name(member).removeprefix('m')


def _type_param_names(member: Declaration) -> frozenset[str]:
    return frozenset(param.name for param in member.type_parameters)


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
        target = _erase_target(target.lstrip('~'))
        _note_context(env, refnode, target)

        # A leading tilde shows only the last component of the name
        if not has_explicit_title and title[0:1] == '~':
            title = _erase_type_arguments(title.partition('(')[0])
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

        # The objects whose names end with the target, or failing that whose basenames do
        suffix = '.' + target
        matches = sorted(fullname for fullname in objects if fullname.endswith(suffix))
        if not matches:
            basename_suffix = suffix.partition('(')[0]
            matches = sorted(fullname for fullname, (_docname, _objtype, basename) in objects.items()
                             if basename.endswith(basename_suffix))
        if not matches:
            return None

        # The overloads of one method are one target, which resolves to the first by name
        if len({objects[fullname][2] for fullname in matches}) > 1:
            logger.warning(__('more than one target found for cross-reference %r: %s'), target, ', '.join(matches),
                           type='ref', subtype='java', location=node)
        return matches[0]

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

    def _resolve(self, env: BuildEnvironment, fromdocname: str, builder: Builder, target: str, node: pending_xref,
                 contnode: Element) -> tuple[str | None, nodes.reference | None]:
        """ The full name of the object that a reference points to, and the reference node """
        if node.get('java:plain'):
            return None, None
        fullname = self.find_object(target, node)
        if fullname:
            docname, objtype, _basename = self.objects[fullname]
            return fullname, make_refnode(builder, fromdocname, docname, _anchor(fullname, objtype), contnode, fullname)

        ref = self.external_ref(env.config, target, node)
        if ref:
            ref.append(contnode)
        return None, ref

    def resolve_xref(self, env: BuildEnvironment, fromdocname: str, builder: Builder, typ: str, target: str,
                     node: pending_xref, contnode: Element) -> nodes.reference | None:
        return self._resolve(env, fromdocname, builder, target, node, contnode)[1]

    def resolve_any_xref(self, env: BuildEnvironment, fromdocname: str, builder: Builder, target: str,
                         node: pending_xref, contnode: Element) -> list[tuple[str, nodes.reference]]:
        fullname, ref = self._resolve(env, fromdocname, builder, target, node, contnode)
        if ref is None:
            return []
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
