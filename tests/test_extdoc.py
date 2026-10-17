from types import SimpleNamespace

import pytest
from conftest import references, warnings

from sphinx_java.extdoc import get_javadoc_ref

URL_MAP = {
    'org.example': ('https://example.org/api', 'javadoc'),
    'org.example.sub': ('https://example.org/sub-api/', 'javadoc8'),
    'com.sphinx': ('https://sphinx.example.com', 'sphinx'),
}


@pytest.mark.parametrize('target, url', [
    ('java.util.List', 'https://docs.oracle.com/javase/8/docs/api/java/util/List.html'),
    ('java.util', 'https://docs.oracle.com/javase/8/docs/api/java/util/package-summary.html'),
    ('java.util.Map.Entry', 'https://docs.oracle.com/javase/8/docs/api/java/util/Map.Entry.html'),
    ('java.util.List.get(int)', 'https://docs.oracle.com/javase/8/docs/api/java/util/List.html#get-int-'),
    ('javax.swing.JFrame', 'https://docs.oracle.com/javase/8/docs/api/javax/swing/JFrame.html'),
    ('org.example.Foo', 'https://example.org/api/org/example/Foo.html'),
    ('org.example.Foo.bar(int)', 'https://example.org/api/org/example/Foo.html#bar(int)'),
    ('org.example.sub.Foo.bar(int)', 'https://example.org/sub-api/org/example/sub/Foo.html#bar-int-'),
    ('com.sphinx.Foo.Bar', 'https://sphinx.example.com/com/sphinx/Foo-Bar.html'),
    ('com.sphinx.sub', 'https://sphinx.example.com/com/sphinx/sub/package-index.html'),
    ('com.sphinx.Foo.bar()', 'https://sphinx.example.com/com/sphinx/Foo.html#com.sphinx.Foo.bar()'),
])
def test_url(target, url):
    ref = get_javadoc_ref(SimpleNamespace(javadoc_url_map=URL_MAP), target, target)
    assert ref is not None
    assert ref['refuri'] == url


@pytest.mark.parametrize('target', ['org.other.Foo', 'Foo', 'org.examples.Foo', 'java', 'org.xml'])
def test_no_source(target):
    assert get_javadoc_ref(SimpleNamespace(javadoc_url_map=URL_MAP), target, target) is None


def test_mapped_package():
    ref = get_javadoc_ref(SimpleNamespace(javadoc_url_map=URL_MAP), 'org.example', 'org.example')
    assert ref is not None
    assert ref['refuri'] == 'https://example.org/api/org/example/package-summary.html'


def test_override_java_se():
    config = SimpleNamespace(javadoc_url_map={'java': ('https://docs.example.com/api', 'javadoc')})
    ref = get_javadoc_ref(config, 'java.util.List', 'java.util.List')
    assert ref is not None
    assert ref['refuri'] == 'https://docs.example.com/api/java/util/List.html'


def test_invalid_type():
    config = SimpleNamespace(javadoc_url_map={'org': ('https://example.org', 'other')})
    with pytest.raises(ValueError, match='invalid target specifier other'):
        get_javadoc_ref(config, 'org.Foo', 'org.Foo')


def test_role(build):
    app = build(':java:extdoc:`java.util.List`, :java:extdoc:`~java.util.Map`, '
                ':java:extdoc:`the list <java.util.List>`')
    assert warnings(app) == []
    assert references(app) == {
        'java.util.List': 'https://docs.oracle.com/javase/8/docs/api/java/util/List.html',
        'Map': 'https://docs.oracle.com/javase/8/docs/api/java/util/Map.html',
        'the list': 'https://docs.oracle.com/javase/8/docs/api/java/util/List.html',
    }


def test_role_unknown(build):
    app = build(':java:extdoc:`org.other.Foo`')
    assert any('no Javadoc source found for org.other.Foo' in line for line in warnings(app))


def test_config_unchanged(build):
    app = build(':java:type:`String`', javadoc_url_map={})
    assert app.config.javadoc_url_map == {}


def test_method_without_package():
    assert get_javadoc_ref(SimpleNamespace(javadoc_url_map=URL_MAP), 'sort(List)', 'sort(List)') is None
