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

from . import _javalang as javalang
from . import extdoc, formatter

logger = logging.getLogger(__name__)

# Classes in java.lang. These are available without an import.
java_dot_lang = {'AbstractMethodError', 'Appendable', 'ArithmeticException', 'ArrayIndexOutOfBoundsException',
                 'ArrayStoreException', 'AssertionError', 'AutoCloseable', 'Boolean', 'BootstrapMethodError',
                 'Byte', 'Character', 'CharSequence', 'Class', 'ClassCastException', 'ClassCircularityError',
                 'ClassFormatError', 'ClassLoader', 'ClassNotFoundException', 'ClassValue', 'Cloneable',
                 'CloneNotSupportedException', 'Comparable', 'Compiler', 'Deprecated', 'Double', 'Enum',
                 'EnumConstantNotPresentException', 'Error', 'Exception', 'ExceptionInInitializerError',
                 'Float', 'IllegalAccessError', 'IllegalAccessException', 'IllegalArgumentException',
                 'IllegalMonitorStateException', 'IllegalStateException', 'IllegalThreadStateException',
                 'IncompatibleClassChangeError', 'IndexOutOfBoundsException', 'InheritableThreadLocal',
                 'InstantiationError', 'InstantiationException', 'Integer', 'InternalError',
                 'InterruptedException', 'Iterable', 'LinkageError', 'Long', 'Math',
                 'NegativeArraySizeException', 'NoClassDefFoundError', 'NoSuchFieldError',
                 'NoSuchFieldException', 'NoSuchMethodError', 'NoSuchMethodException', 'NullPointerException',
                 'Number', 'NumberFormatException', 'Object', 'OutOfMemoryError', 'Override', 'Package',
                 'Process', 'ProcessBuilder', 'Readable', 'ReflectiveOperationException', 'Runnable', 'Runtime',
                 'RuntimeException', 'RuntimePermission', 'SafeVarargs', 'SecurityException', 'SecurityManager',
                 'Short', 'StackOverflowError', 'StackTraceElement', 'StrictMath', 'String', 'StringBuffer',
                 'StringBuilder', 'StringIndexOutOfBoundsException', 'SuppressWarnings', 'System', 'Thread',
                 'ThreadDeath', 'ThreadGroup', 'ThreadLocal', 'Throwable', 'TypeNotPresentException',
                 'UnknownError', 'UnsatisfiedLinkError', 'UnsupportedClassVersionError',
                 'UnsupportedOperationException', 'VerifyError', 'VirtualMachineError', 'Void'}


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

        package = self.env.ref_context.get('java:imports', {}).get(target, None)

        if not package and target in java_dot_lang:
            package = 'java.lang'

        if package:
            ref['java:imported'] = True
            ref['java:package'] = package
        else:
            ref['java:imported'] = False
            ref['java:package'] = self.get_package()

        return ref

    def _type_params(self) -> set[str]:
        """ The names of the type parameters in scope """
        return _type_params_in_scope(self.env) | self.own_type_params

    def _build_type_node(self, typ: Any) -> list[Node]:
        if not isinstance(typ, javalang.tree.ReferenceType):
            type_repr = formatter.output_type(typ).build()
            return [nodes.Text(type_repr)]

        dim = '[]' * len(typ.dimensions) if typ.dimensions else ''
        if not typ.sub_type and not typ.arguments and typ.name in self._type_params():
            return [nodes.Text(typ.name + dim)]

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
            ref_node = self._build_ref_node(target)
            ref_node += nodes.Text(typ.name)
            parts.append(ref_node)

            if typ.arguments:
                parts += self._build_type_args(typ.arguments)

            typ = typ.sub_type

            if typ:
                target = target + '.' + typ.name
                parts.append(nodes.Text('.'))
            elif dim:
                parts.append(nodes.Text(dim))

        return parts

    def _build_type_args(self, type_args: list[Any]) -> list[Node]:
        parts: list[Node] = [nodes.Text('<')]
        for i, type_arg in enumerate(type_args):
            if i > 0:
                parts.append(nodes.Text(', '))

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

    def _build_parameter_list(self, parameters: list[Any]) -> addnodes.desc_parameterlist:
        paramlist = addnodes.desc_parameterlist()
        for parameter in parameters:
            param = addnodes.desc_parameter('', '', noemph=True)
            param += self._build_type_node(parameter.type)

            if parameter.varargs:
                param += nodes.Text('...')

            param += nodes.emphasis(' ' + parameter.name, ' ' + parameter.name)
            paramlist += param
        return paramlist

    @staticmethod
    def _add_modifiers(signode: desc_signature, modifiers: set[str]) -> None:
        mods = formatter.output_modifiers(modifiers).build()
        if mods:
            signode += nodes.Text(mods + ' ')

    @staticmethod
    def _overload_name(member: Any) -> str:
        """ The name of a method or constructor with its parameter types, such as foo(int, List) """
        param_reprs = [formatter.output_type(param.type, with_generics=False).build() for param in member.parameters]
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

        indextext = self.get_index_text(name)
        if indextext:
            self.indexnode['entries'].append(('single', indextext, fullname, '', None))

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
        try:
            member = javalang.parse.parse_member_signature(sig)
        except javalang.parser.JavaSyntaxError:
            raise self.error('syntax error in method signature') from None

        if not isinstance(member, javalang.tree.MethodDeclaration):
            raise self.error('expected method declaration')

        self.own_type_params = _type_param_names(member)
        self._add_modifiers(signode, member.modifiers)

        if member.type_parameters:
            type_params = formatter.output_type_params(member.type_parameters).build()
            signode += nodes.Text(type_params)
            signode += nodes.Text(' ')

        rnode = addnodes.desc_type('', '')
        rnode += self._build_type_node(member.return_type)

        signode += rnode
        signode += nodes.Text(' ')
        signode += addnodes.desc_name(member.name, member.name)
        signode += self._build_parameter_list(member.parameters)

        return self._overload_name(member)

    def get_index_text(self, name: str) -> str:
        return _('%s (Java method)') % name


class JavaConstructor(JavaObject):
    doc_field_types = [
        TypedField('parameter', label=_('Parameters'),
                   names=('param', 'parameter', 'arg', 'argument'),
                   typerolename='type', typenames=('type',)),
        GroupedField('throws', names=('throws',), label=_('Throws'))
    ]

    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        try:
            member = javalang.parse.parse_constructor_signature(sig)
        except javalang.parser.JavaSyntaxError:
            raise self.error('syntax error in constructor signature') from None

        if not isinstance(member, javalang.tree.ConstructorDeclaration):
            raise self.error('expected constructor declaration')
        self.own_type_params = _type_param_names(member)

        self._add_modifiers(signode, member.modifiers)

        signode += addnodes.desc_name(member.name, member.name)
        signode += self._build_parameter_list(member.parameters)

        return self._overload_name(member)

    def get_index_text(self, name: str) -> str:
        return _('%s (Java constructor)') % name


class JavaType(JavaObject):
    doc_field_types = [
        GroupedField('parameter', names=('param',), label=_('Parameters'))
    ]

    declaration_type: str | None = None

    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        try:
            member = javalang.parse.parse_type_signature(sig)
        except javalang.parser.JavaSyntaxError:
            raise self.error('syntax error in field signature') from None

        declaration_types = {
            javalang.tree.ClassDeclaration: 'class',
            javalang.tree.InterfaceDeclaration: 'interface',
            javalang.tree.EnumDeclaration: 'enum',
            javalang.tree.AnnotationDeclaration: 'annotation',
        }
        self.declaration_type = declaration_types.get(type(member))
        if self.declaration_type is None:
            raise self.error('expected type declaration')
        self.own_type_params = _type_param_names(member)

        self._add_modifiers(signode, member.modifiers)

        keyword = '@interface' if self.declaration_type == 'annotation' else self.declaration_type
        signode += nodes.Text(keyword + ' ')

        signode += addnodes.desc_name(member.name, member.name)

        if self.declaration_type in ('class', 'interface') and member.type_parameters:
            type_params = formatter.output_type_params(member.type_parameters).build()
            signode += nodes.Text(type_params)

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
        elif self.declaration_type == 'enum':
            if member.implements:
                signode += nodes.Text(' implements ')
                signode += self._build_type_node_list(member.implements)

        name: str = member.name
        return name

    def get_index_text(self, name: str) -> str:
        return _('%s (Java %s)') % (name, self.declaration_type)


class JavaField(JavaObject):
    def handle_signature(self, sig: str, signode: desc_signature) -> str:
        try:
            member = javalang.parse.parse_member_signature(sig)
        except javalang.parser.JavaSyntaxError:
            raise self.error('syntax error in field signature') from None

        if not isinstance(member, javalang.tree.FieldDeclaration):
            raise self.error('expected field declaration')

        self._add_modifiers(signode, member.modifiers)

        tnode = addnodes.desc_type('', '')
        tnode += self._build_type_node(member.type)

        signode += tnode
        signode += nodes.Text(' ')

        if len(member.declarators) > 1:
            self.error('only one field may be documented at a time')

        declarator = member.declarators[0]
        signode += addnodes.desc_name(declarator.name, declarator.name)

        dim = '[]' * len(declarator.dimensions)
        signode += nodes.Text(dim)

        if declarator.initializer and isinstance(declarator.initializer, javalang.tree.Literal):
            signode += nodes.Text(' = ' + declarator.initializer.value)

        name: str = declarator.name
        return name

    def get_index_text(self, name: str) -> str:
        return _('%s (Java field)') % name


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
        self.env.ref_context.setdefault('java:imports', {})[typename] = package
        return []


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

    package = env.ref_context.get('java:imports', {}).get(basetype, None)

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
    def process_link(self, env: BuildEnvironment, refnode: Element, has_explicit_title: bool, title: str,
                     target: str) -> tuple[str, str]:
        target = target.lstrip('~')
        _note_context(env, refnode, target)

        # A leading tilde shows only the last component of the name
        if not has_explicit_title and title[0:1] == '~':
            title = title.partition('(')[0]
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
        'constructor': ObjType(_('constructor'), 'construct', 'ref'),
        'method': ObjType(_('method'), 'meth', 'ref')
    }

    directives = {
        'package': JavaPackage,
        'type': JavaType,
        'field': JavaField,
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
        if target in java_dot_lang:
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
