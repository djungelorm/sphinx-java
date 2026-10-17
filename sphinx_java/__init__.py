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

from importlib.metadata import version
from typing import Any

from sphinx.application import Sphinx

from .domain import JavaDomain, suppress_missing_reference
from .extdoc import javadoc_role


def setup(app: Sphinx) -> dict[str, Any]:
    app.add_domain(JavaDomain)

    app.add_config_value('javadoc_url_map', {}, 'env', types=(dict,))
    app.add_role('java:extdoc', javadoc_role)
    app.connect('warn-missing-reference', suppress_missing_reference)

    return {
        'version': version('sphinx-java'),
        'env_version': 1,
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
