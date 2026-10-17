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

from collections.abc import Sequence
from typing import Any

from docutils import nodes, utils
from docutils.nodes import Node, system_message
from docutils.parsers.rst.states import Inliner
from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx.errors import ConfigError
from sphinx.locale import __
from sphinx.util.nodes import split_explicit_title

from .javase_modules import JAVA_SE_MODULES

# The Java SE packages, which link to the Java SE docs unless javadoc_url_map has them
JAVA_SE_PACKAGES = ('java', 'javax', 'org.ietf', 'org.xml', 'org.w3c')


def check_config(app: Sphinx, config: Config) -> None:
    version = config.javadoc_java_se_version
    if version != 8 and version < 11:
        raise ConfigError(__('javadoc_java_se_version must be 8, or 11 or later, not %r') % version)


def _java_se_docs(version: int) -> tuple[str, str]:
    """ The base URL and docs type of the Java SE docs """
    if version == 8:
        return 'https://docs.oracle.com/javase/8/docs/api', 'javadoc8'
    return f'https://docs.oracle.com/en/java/javase/{version}/docs/api', 'javadoc11'


def _find_source(config: Config, text: str) -> tuple[str, str] | None:
    """ The base URL and docs type for the longest package that contains text """
    javadoc_url_map: dict[str, tuple[str, str]] = {
        **dict.fromkeys(JAVA_SE_PACKAGES, _java_se_docs(config.javadoc_java_se_version)),
        **{package: source for package, source in config.javadoc_url_map.items() if source},
    }
    # Note: The Java SE prefixes, such as java, are not packages themselves.
    matches = [package for package in javadoc_url_map if text.startswith(package + '.')
               or (text == package and package in config.javadoc_url_map)]
    if not matches:
        return None
    return javadoc_url_map[max(matches, key=len)]


def _javadoc_anchor(ext_type: str, cls: str, method: str) -> str:
    name, _, params = method.partition('(')
    if ext_type == 'javadoc8':
        # Parameters are separated by dashes, and arrays are written :A
        param_types = [param.strip().replace('[]', ':A') for param in params.rstrip(')').split(',')]
        return name + '-' + '-'.join(filter(None, param_types)) + '-'
    if ext_type == 'javadoc11':
        # Constructors are named <init>
        if name == cls.rpartition('.')[2]:
            name = '%3Cinit%3E'
        return name + '(' + params.replace(' ', '')
    return method


def _build_url(baseurl: str, ext_type: str, package: str, cls: str, method: str | None) -> str:
    if not baseurl.endswith('/'):
        baseurl = baseurl + '/'
    if ext_type == 'javadoc11' and package in JAVA_SE_MODULES:
        baseurl += JAVA_SE_MODULES[package] + '/'
    path = baseurl + package.replace('.', '/') + '/'

    if ext_type in ('javadoc', 'javadoc8', 'javadoc11'):
        url = path + (cls or 'package-summary') + '.html'
        if method:
            url += '#' + _javadoc_anchor(ext_type, cls, method)
    elif ext_type == 'sphinx':
        url = path + (cls.replace('.', '-') or 'package-index') + '.html'
        if method:
            url += '#' + package + '.' + (cls or 'package-index') + '.' + method
    else:
        raise ValueError('invalid target specifier ' + ext_type)
    return url


def get_javadoc_ref(config: Config, rawtext: str, text: str) -> nodes.reference | None:
    """ A reference to the external docs for a fully qualified name, or None if no docs are configured for it """
    method = None

    if '(' in text:
        # A method reference with no package, such as #sort(List), has no dot before the bracket
        try:
            split_point = text.rindex('.', 0, text.index('('))
            method = text[split_point + 1:]
            text = text[:split_point]
        except ValueError:
            pass

    source = _find_source(config, text)
    if not source:
        return None

    package_parts = []
    cls_parts: list[str] = []

    for part in text.split('.'):
        if cls_parts or part[0].isupper():
            cls_parts.append(part)
        else:
            package_parts.append(part)

    package = '.'.join(package_parts)
    cls = '.'.join(cls_parts)

    title = '.'.join(filter(None, (package, cls, method)))
    node = nodes.reference(rawtext, '')
    node['refuri'] = _build_url(*source, package, cls, method)
    node['reftitle'] = title

    return node


def javadoc_role(name: str, rawtext: str, text: str, lineno: int, inliner: Inliner,
                 options: dict[str, Any] | None = None,
                 content: Sequence[str] = ()) -> tuple[list[Node], list[system_message]]:
    """ Role for linking to external Javadoc """

    has_explicit_title, title, target = split_explicit_title(text)
    title = utils.unescape(title)
    target = utils.unescape(target)

    if not has_explicit_title:
        target = target.lstrip('~')

        if title[0] == '~':
            title = title[1:].rpartition('.')[2]

    config = inliner.document.settings.env.config
    ref = get_javadoc_ref(config, rawtext, target)

    if not ref:
        msg = inliner.reporter.warning(f'no Javadoc source found for {target} in javadoc_url_map', line=lineno)
        return [inliner.problematic(rawtext, rawtext, msg)], [msg]

    ref.append(nodes.Text(title))

    return [ref], []
