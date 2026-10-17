from pathlib import Path

import pytest
from docutils import nodes
from sphinx import addnodes, version_info
from sphinx.util.console import strip_colors

pytest_plugins = ['sphinx.testing.fixtures']


@pytest.fixture(scope='session')
def rootdir():
    return Path(__file__).parent / 'roots'


@pytest.fixture
def build(make_app, tmp_path):
    """ Build a project from reStructuredText for the index and any other pages, and return the app """
    def _build(rst, pages=None, parallel=0, **confoverrides):
        (tmp_path / 'conf.py').write_text("extensions = ['sphinx_java']\n")
        (tmp_path / 'index.rst').write_text(rst)
        for name, page in (pages or {}).items():
            (tmp_path / f'{name}.rst').write_text(page)
        app = make_app('html', srcdir=tmp_path, parallel=parallel,
                       confoverrides={'nitpicky': True, **confoverrides})
        app.build()
        return app
    return _build


def resolved_doctree(app, docname='index'):
    # Sphinx 9 deprecates calls without tags, and earlier versions reject the argument
    kwargs = {'tags': app.tags} if version_info >= (9,) else {}
    return app.env.get_and_resolve_doctree(docname, app.builder, **kwargs)


# Note: SphinxTestApp.warning was added in Sphinx 7.3.
def warnings(app):
    return [strip_colors(line) for line in app._warning.getvalue().splitlines() if line.strip()]


def signatures(app):
    """ Map each object id on the index page to its rendered signature text """
    doctree = resolved_doctree(app)
    return {node_id: node.astext().replace('\xa0', ' ')
            for node in doctree.findall(addnodes.desc_signature)
            for node_id in node['ids']}


def references(app, docname='index'):
    """ Map each linked name on a page to its target """
    doctree = resolved_doctree(app, docname)
    return {ref.astext(): ref.get('refid') or ref.get('refuri')
            for ref in doctree.findall(nodes.reference) if 'internal' in ref or 'refuri' in ref}
