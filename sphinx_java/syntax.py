#
# Copyright 2026 djungelorm
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

""" Parse Java declaration signatures with tree-sitter into a small syntax model """

import re
from dataclasses import dataclass, field
from typing import cast

import tree_sitter_java
from tree_sitter import Language, Node, Parser

PARSER = Parser(Language(tree_sitter_java.language()))

# The source each kind of signature is wrapped in to make a compilation unit, tried in order
WRAPPERS = {
    'type': [('', ' {}')],
    'method': [('class _ { ', '; }'), ('@interface _ { ', '; }')],
    'field': [('class _ { ', '; }')],
    'constructor': [('class _ { ', ' {} }'), ('record _() { ', ' {} }')],
    'enumconstant': [('enum _ { ', ' }')],
}

# The kind of declaration for each tree-sitter node type
KINDS = {
    'class_declaration': 'class',
    'interface_declaration': 'interface',
    'enum_declaration': 'enum',
    'annotation_type_declaration': 'annotation',
    'record_declaration': 'record',
    'method_declaration': 'method',
    'annotation_type_element_declaration': 'method',
    'constructor_declaration': 'constructor',
    'compact_constructor_declaration': 'constructor',
    'field_declaration': 'field',
    'enum_constant': 'enumconstant',
}

# The attribute of a declaration for each clause listing types
CLAUSES = {
    'throws': 'throws',
    'superclass': 'extends',
    'extends_interfaces': 'extends',
    'super_interfaces': 'implements',
    'permits': 'permits',
}

TYPE_KINDS = ('class', 'interface', 'enum', 'annotation', 'record')

ANNOTATIONS = ('annotation', 'marker_annotation')

# String and character literals, and the ... of a varargs parameter
VARARGS = re.compile(rb'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|(\.\.\.)')


class JavaSyntaxError(Exception):
    pass


@dataclass
class Annotation:
    name: str
    # The arguments as written, such as ("unchecked"), or empty
    arguments: str = ''


@dataclass
class Segment:
    """ One name in a type, such as Map or Entry<K, V> in Map.Entry<K, V> """
    name: str
    annotations: list[Annotation] = field(default_factory=list)
    arguments: list['TypeArgument'] = field(default_factory=list)


@dataclass
class Type:
    segments: list[Segment]
    # The annotations of each array dimension
    dimensions: list[list[Annotation]] = field(default_factory=list)

    @classmethod
    def named(cls, name: str) -> 'Type':
        """ The type for a qualified name, such as java.io.IOException """
        return cls([Segment(part) for part in name.split('.')])


@dataclass
class TypeArgument:
    # None for a type, ? for an unbounded wildcard, or the bound of a wildcard, extends or super
    wildcard: str | None
    type: Type | None = None
    annotations: list[Annotation] = field(default_factory=list)


@dataclass
class TypeParameter:
    name: str
    bounds: list[Type]
    annotations: list[Annotation]


@dataclass
class Modifiers:
    modifiers: set[str] = field(default_factory=set)
    # The annotations before the first modifier, and the annotations after it
    annotations: list[Annotation] = field(default_factory=list)
    annotations_after_modifiers: list[Annotation] = field(default_factory=list)


@dataclass
class Parameter(Modifiers):
    type: Type = field(default_factory=lambda: Type([]))
    name: str = ''
    varargs: bool = False
    varargs_annotations: list[Annotation] = field(default_factory=list)
    receiver: bool = False


@dataclass
class Declaration(Modifiers):
    kind: str = ''
    name: str = ''
    type_parameters: list[TypeParameter] = field(default_factory=list)
    # The return type of a method, or the type of a field
    type: Type | None = None
    # The parameters of a method or constructor, or the components of a record. None for a compact constructor.
    parameters: list[Parameter] | None = None
    throws: list[Type] = field(default_factory=list)
    extends: list[Type] = field(default_factory=list)
    implements: list[Type] = field(default_factory=list)
    permits: list[Type] = field(default_factory=list)
    # The array dimensions after the name of a field
    dimensions: int = 0
    # The number of variables a field declares
    declarators: int = 1
    # The initializer of a field, the default value of an annotation element, or the arguments of an enum
    # constant, as written
    value: str | None = None


def parse(kind: str, sig: str) -> Declaration:
    """ Parse a signature of a type, method, field, constructor or enum constant """
    sig = sig.strip().removesuffix(';').rstrip()
    for prefix, suffix in WRAPPERS[kind]:
        source = (prefix + sig + suffix).encode()
        # Note: the tree-sitter-java 0.23.5 grammar has no annotations before ..., so we parse ... as [] and mark it
        # (https://github.com/tree-sitter/tree-sitter-java/issues/205)
        varargs = {m.start(1) for m in VARARGS.finditer(source) if m.group(1)}
        for start in varargs:
            source = source[:start] + b'[] ' + source[start + 3:]
        root = PARSER.parse(source).root_node
        if root.has_error:
            continue
        node = _only_child(root)
        if prefix:
            node = _only_child(_child(node, 'body'))
        if node is None or node.type not in KINDS or (kind == 'type') != (KINDS[node.type] in TYPE_KINDS):
            break
        builder = _Builder(varargs)
        declaration = builder.declaration(node)
        if builder.varargs:
            break
        return declaration
    raise JavaSyntaxError


def _only_child(node: Node | None) -> Node | None:
    children = node.named_children if node else []
    return children[0] if len(children) == 1 else None


def _child(node: Node | None, name: str) -> Node | None:
    return node.child_by_field_name(name) if node else None


def _text(node: Node) -> str:
    return cast(bytes, node.text).decode()


def _name(node: Node) -> str:
    """ The text of a name, without whitespace """
    return ''.join(_text(node).split())


class _Builder:
    def __init__(self, varargs: set[int]):
        # The positions of the ... marks not yet consumed by a parameter
        self.varargs = set(varargs)

    def declaration(self, node: Node) -> Declaration:
        # A field has its name, dimensions and initializer on its first declarator
        declarators = [n for n in node.named_children if n.type == 'variable_declarator']
        declarator = declarators[0] if declarators else node
        declaration = Declaration(kind=KINDS[node.type], name=_name(cast(Node, _child(declarator, 'name'))),
                                  declarators=len(declarators) or 1)
        self.modifiers(declaration, node)

        type_params = _child(node, 'type_parameters')
        if type_params:
            declaration.type_parameters = [self.type_parameter(n) for n in type_params.named_children]

        typ = _child(node, 'type')
        if typ:
            declaration.type = self.type(typ)
            # Annotations between the type parameters and the return type
            before_type = node.children[:node.children.index(typ)]
            declaration.type.segments[0].annotations[:0] = [
                self.annotation(n) for n in before_type if n.type in ANNOTATIONS]
            dims = _child(node, 'dimensions')
            if dims:
                declaration.type.dimensions += self.dimensions(dims)

        parameters = _child(node, 'parameters')
        if parameters:
            declaration.parameters = [self.parameter(n) for n in parameters.named_children]
        elif node.type in ('method_declaration', 'annotation_type_element_declaration', 'constructor_declaration'):
            declaration.parameters = []

        for child in node.named_children:
            if child.type in CLAUSES:
                setattr(declaration, CLAUSES[child.type], self.types(child))

        value = _child(declarator, 'value') or _child(node, 'arguments')
        if value:
            declaration.value = _text(value)

        dims = _child(declarator, 'dimensions')
        if declarators and dims:
            declaration.dimensions = len(self.dimensions(dims))
        return declaration

    def modifiers(self, target: Modifiers, node: Node) -> None:
        modifiers = next((n for n in node.children if n.type == 'modifiers'), None)
        for child in modifiers.children if modifiers else []:
            if child.type not in ANNOTATIONS:
                target.modifiers.add(child.type)
            elif target.modifiers:
                target.annotations_after_modifiers.append(self.annotation(child))
            else:
                target.annotations.append(self.annotation(child))

    def annotation(self, node: Node) -> Annotation:
        arguments = _child(node, 'arguments')
        return Annotation(_name(cast(Node, _child(node, 'name'))), _text(arguments) if arguments else '')

    def annotations(self, node: Node) -> list[Annotation]:
        return [self.annotation(n) for n in node.named_children if n.type in ANNOTATIONS]

    def dimensions(self, node: Node) -> list[list[Annotation]]:
        """ The annotations of each dimension """
        dims: list[list[Annotation]] = []
        annotations: list[Annotation] = []
        for child in node.children:
            if child.type in ANNOTATIONS:
                annotations.append(self.annotation(child))
            elif child.type == ']':
                dims.append(annotations)
                annotations = []
        return dims

    def types(self, node: Node) -> list[Type]:
        """ The types in a throws, extends, implements or permits clause """
        types = node.named_children
        if types[0].type == 'type_list':
            types = types[0].named_children
        return [self.type(n) for n in types]

    def type(self, node: Node) -> Type:
        if node.type == 'array_type':
            typ = self.type(cast(Node, _child(node, 'element')))
            typ.dimensions += self.dimensions(cast(Node, _child(node, 'dimensions')))
            return typ
        if node.type == 'annotated_type':
            typ = self.type(node.named_children[-1])
            typ.segments[0].annotations[:0] = self.annotations(node)
            return typ
        if node.type == 'generic_type':
            typ = self.type(node.named_children[0])
            typ.segments[-1].arguments = [
                self.type_argument(n) for n in node.named_children[1].named_children]
            return typ
        if node.type == 'scoped_type_identifier':
            typ = self.type(node.named_children[0])
            typ.segments.append(Segment(_text(node.named_children[-1]), self.annotations(node)))
            return typ
        return Type([Segment(_text(node))])

    def type_argument(self, node: Node) -> TypeArgument:
        if node.type != 'wildcard':
            return TypeArgument(None, self.type(node))
        annotations = self.annotations(node)
        bound = next((n.type for n in node.children if n.type in ('extends', 'super')), None)
        if bound is None:
            return TypeArgument('?', annotations=annotations)
        return TypeArgument(bound, self.type(node.named_children[-1]), annotations)

    def type_parameter(self, node: Node) -> TypeParameter:
        name = next(n for n in node.named_children if n.type == 'type_identifier')
        bound = next((n for n in node.named_children if n.type == 'type_bound'), None)
        bounds = [self.type(n) for n in bound.named_children] if bound else []
        return TypeParameter(_text(name), bounds, self.annotations(node))

    def parameter(self, node: Node) -> Parameter:
        parameter = Parameter()
        if node.type == 'receiver_parameter':
            # The annotations, the type, then the name, such as Outer.this
            parameter.annotations = self.annotations(node)
            typ = next(n for n in node.named_children if n.type not in ANNOTATIONS)
            parameter.type = self.type(typ)
            parameter.name = ''.join(_text(n) for n in node.children[node.children.index(typ) + 1:])
            parameter.receiver = True
            return parameter

        self.modifiers(parameter, node)
        type_node = cast(Node, _child(node, 'type'))
        parameter.type = self.type(type_node)
        parameter.name = _name(cast(Node, _child(node, 'name')))
        parameter.receiver = parameter.name == 'this'

        # The last dimension of a varargs parameter is its ..., parsed as []
        if type_node.type == 'array_type':
            brackets = [n for n in cast(Node, _child(type_node, 'dimensions')).children if n.type == '[']
            if brackets[-1].start_byte in self.varargs:
                self.varargs.remove(brackets[-1].start_byte)
                parameter.varargs = True
                parameter.varargs_annotations = parameter.type.dimensions.pop()

        dims = _child(node, 'dimensions')
        if dims:
            parameter.type.dimensions += self.dimensions(dims)
        return parameter
