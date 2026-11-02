from types import SimpleNamespace

import pytest
from conftest import references, warnings
from sphinx.errors import ConfigError

from sphinx_java.extdoc import get_javadoc_ref

URL_MAP = {
    'org.example': ('https://example.org/api', 'javadoc'),
    'org.example.sub': ('https://example.org/sub-api/', 'javadoc8'),
    'com.sphinx': ('https://sphinx.example.com', 'sphinx'),
}


JAVA_8 = 'https://docs.oracle.com/javase/8/docs/api/'
JAVA_25 = 'https://docs.oracle.com/en/java/javase/25/docs/api/'


def config(url_map=None, version=25):
    return SimpleNamespace(javadoc_url_map=URL_MAP if url_map is None else url_map, javadoc_java_se_version=version)


@pytest.mark.parametrize('target, url', [
    ('java.util.List', JAVA_25 + 'java.base/java/util/List.html'),
    ('java.util', JAVA_25 + 'java.base/java/util/package-summary.html'),
    ('java.util.Map.Entry', JAVA_25 + 'java.base/java/util/Map.Entry.html'),
    ('java.util.List.get(int)', JAVA_25 + 'java.base/java/util/List.html#get(int)'),
    ('java.util.List.subList(int, int)', JAVA_25 + 'java.base/java/util/List.html#subList(int,int)'),
    ('java.util.ArrayList.ArrayList(int)', JAVA_25 + 'java.base/java/util/ArrayList.html#%3Cinit%3E(int)'),
    ('java.util.Map.Entry.getKey()', JAVA_25 + 'java.base/java/util/Map.Entry.html#getKey()'),
    ('javax.swing.JFrame', JAVA_25 + 'java.desktop/javax/swing/JFrame.html'),
    ('org.w3c.dom.Node', JAVA_25 + 'java.xml/org/w3c/dom/Node.html'),
    ('org.ietf.jgss.GSSName', JAVA_25 + 'java.security.jgss/org/ietf/jgss/GSSName.html'),
    ('org.example.Foo', 'https://example.org/api/org/example/Foo.html'),
    ('org.example.Foo.bar(int)', 'https://example.org/api/org/example/Foo.html#bar(int)'),
    ('org.example.sub.Foo.bar(int)', 'https://example.org/sub-api/org/example/sub/Foo.html#bar-int-'),
    ('com.sphinx.Foo.Bar', 'https://sphinx.example.com/com/sphinx/Foo-Bar.html'),
    ('com.sphinx.sub', 'https://sphinx.example.com/com/sphinx/sub/package-index.html'),
    ('com.sphinx.Foo.bar()', 'https://sphinx.example.com/com/sphinx/Foo.html#com.sphinx.Foo.bar()'),
])
def test_url(target, url):
    ref = get_javadoc_ref(config(), target, target)
    assert ref is not None
    assert ref['refuri'] == url


@pytest.mark.parametrize('version, target, url', [
    (8, 'java.util.List', JAVA_8 + 'java/util/List.html'),
    (8, 'java.util.List.get(int)', JAVA_8 + 'java/util/List.html#get-int-'),
    (8, 'java.util.List.subList(int, int)', JAVA_8 + 'java/util/List.html#subList-int-int-'),
    (8, 'java.util.List.size()', JAVA_8 + 'java/util/List.html#size--'),
    (8, 'java.lang.String.String(char[])', JAVA_8 + 'java/lang/String.html#String-char:A-'),
    (8, 'java.lang.String.format(java.lang.String, java.lang.Object...)',
     JAVA_8 + 'java/lang/String.html#format-java.lang.String-java.lang.Object...-'),
    (8, 'javax.swing.JFrame', JAVA_8 + 'javax/swing/JFrame.html'),
    (11, 'java.util.List', 'https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/util/List.html'),
])
def test_java_se_version(version, target, url):
    ref = get_javadoc_ref(config(version=version), target, target)
    assert ref is not None
    assert ref['refuri'] == url


def test_javadoc11_without_module():
    ref = get_javadoc_ref(config({'org.example': ('https://example.org/api', 'javadoc11')}),
                          'org.example.Foo.Foo(int, int)', 'org.example.Foo.Foo(int, int)')
    assert ref is not None
    assert ref['refuri'] == 'https://example.org/api/org/example/Foo.html#%3Cinit%3E(int,int)'


@pytest.mark.parametrize('version', [7, 9, 10])
def test_invalid_java_se_version(build, version):
    with pytest.raises(ConfigError, match=f'javadoc_java_se_version must be 8, or 11 or later, not {version}'):
        build('', javadoc_java_se_version=version)


@pytest.mark.parametrize('target', ['org.other.Foo', 'Foo', 'org.examples.Foo', 'java', 'org.xml', 'java.util.',
                                    'java..List'])
def test_no_source(target):
    assert get_javadoc_ref(config(), target, target) is None


def test_mapped_package():
    ref = get_javadoc_ref(config(), 'org.example', 'org.example')
    assert ref is not None
    assert ref['refuri'] == 'https://example.org/api/org/example/package-summary.html'


def test_override_java_se():
    url_map = {'java': ('https://docs.example.com/api', 'javadoc')}
    ref = get_javadoc_ref(config(url_map), 'java.util.List', 'java.util.List')
    assert ref is not None
    assert ref['refuri'] == 'https://docs.example.com/api/java/util/List.html'


def test_invalid_type(build):
    with pytest.raises(ConfigError, match="javadoc_url_map has an unknown docs type 'other' for org"):
        build('', javadoc_url_map={'org': ('https://example.org', 'other')})


def test_role(build):
    app = build(':java:extdoc:`java.util.List`, :java:extdoc:`~java.util.Map`, '
                ':java:extdoc:`the list <java.util.List>`')
    assert warnings(app) == []
    assert references(app) == {
        'java.util.List': 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html',
        'Map': 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html',
        'the list': 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html',
    }


def test_role_unknown(build):
    app = build(':java:extdoc:`org.other.Foo`')
    assert any('no Javadoc source found for org.other.Foo' in line for line in warnings(app))


def test_role_empty_part(build):
    app = build(':java:extdoc:`java.util.`, :java:type:`java.util.`')
    assert any('no Javadoc source found for java.util.' in line for line in warnings(app))
    assert any('java:type reference target not found: java.util.' in line for line in warnings(app))


def test_config_unchanged(build):
    app = build(':java:type:`String`', javadoc_url_map={})
    assert app.config.javadoc_url_map == {}


def test_method_without_package():
    assert get_javadoc_ref(config(), 'sort(List)', 'sort(List)') is None
