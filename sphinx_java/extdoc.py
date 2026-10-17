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

import re
from collections.abc import Sequence
from typing import Any

from docutils import nodes, utils
from docutils.nodes import Node, system_message
from docutils.parsers.rst.states import Inliner
from sphinx.config import Config
from sphinx.util.nodes import split_explicit_title

# The Java SE packages, which link to the Java SE docs unless javadoc_url_map has them
JAVA_SE_DOCS = ('http://docs.oracle.com/javase/8/docs/api', 'javadoc8')
JAVA_SE_PACKAGES = ('java', 'javax', 'org.xml', 'org.w3c')


def get_javadoc_ref(config: Config, rawtext: str, text: str) -> nodes.reference | None:
    """ A reference to the external docs for a fully qualified name, or None if no docs are configured for it """
    javadoc_url_map: dict[str, tuple[str, str]] = {
        **{package: JAVA_SE_DOCS for package in JAVA_SE_PACKAGES},
        **{package: source for package, source in config.javadoc_url_map.items() if source},
    }

    source = None
    package = ''
    method = None

    if '(' in text:
        # A method reference with no package, such as #sort(List), has no dot before the bracket
        try:
            split_point = text.rindex('.', 0, text.index('('))
            method = text[split_point + 1:]
            text = text[:split_point]
        except ValueError:
            pass

    # The longest matching package
    for pkg, (baseurl, ext_type) in javadoc_url_map.items():
        if text.startswith(pkg + '.') and len(pkg) > len(package):
            source = baseurl, ext_type
            package = pkg

    if not source:
        return None

    baseurl, ext_type = source

    package_parts = []
    cls_parts: list[str] = []

    for part in text.split('.'):
        if cls_parts or part[0].isupper():
            cls_parts.append(part)
        else:
            package_parts.append(part)

    package = '.'.join(package_parts)
    cls = '.'.join(cls_parts)

    if not baseurl.endswith('/'):
        baseurl = baseurl + '/'

    if ext_type == 'javadoc':
        if not cls:
            cls = 'package-summary'
        url = baseurl + package.replace('.', '/') + '/' + cls + '.html'
        if method:
            url = url + '#' + method
    elif ext_type == 'javadoc8':
        if not cls:
            cls = 'package-summary'
        url = baseurl + package.replace('.', '/') + '/' + cls + '.html'
        if method:
            url = url + '#' + re.sub(r'[()]', '-', method)
    elif ext_type == 'sphinx':
        if not cls:
            cls = 'package-index'
        url = baseurl + package.replace('.', '/') + '/' + cls.replace('.', '-') + '.html'
        if method:
            url = url + '#' + package + '.' + cls + '.' + method
    else:
        raise ValueError('invalid target specifier ' + ext_type)

    title = '.'.join(filter(None, (package, cls, method)))
    node = nodes.reference(rawtext, '')
    node['refuri'] = url
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
        raise ValueError(f'no Javadoc source found for {target} in javadoc_url_map')

    ref.append(nodes.Text(title))

    return [ref], []
