import pytest
from conftest import references, resolved_doctree, signatures, warnings
from sphinx import addnodes

SOURCE = '''
.. java:package:: com.example

.. java:import:: java.util List

.. java:type:: public class Box<T extends Comparable<T>> extends Base implements java.io.Serializable, Other

   .. java:constructor:: public Box(T value)

   .. java:method:: public static <U> List<U> wrap(U[] items, String... names)

   .. java:method:: String getName()

   .. java:method:: void setName(String name)

      :param String name: The name.

   .. java:field:: public static final int SIZE = 10

   .. java:field:: List<? extends Number> counts

.. java:type:: public interface Other extends Comparable<Other>

.. java:type:: public class Base

.. java:type:: public enum Color implements Other

.. java:type:: public @interface Marker

References: :java:type:`Box`, :java:meth:`Box.wrap`, :java:ref:`~com.example.Box.getName()`,
:java:field:`Box.SIZE`, :java:type:`String`, :java:extdoc:`java.util.List`.
'''


@pytest.fixture
def app(build):
    return build(SOURCE)


@pytest.mark.xfail(reason='type parameters and package names are references')
def test_no_warnings(app):
    assert warnings(app) == []


@pytest.mark.parametrize('node_id, text', [
    ('com.example.Box',
     'public class Box<T extends Comparable<T>> extends Base implements java.io.Serializable, Other'),
    ('com.example.Box.Box(T)', 'public Box(T value)'),
    ('com.example.Box.wrap(U[], String)', 'public static <U> List<U> wrap(U[] items, String... names)'),
    ('com.example.Box.SIZE', 'public static final int SIZE = 10'),
    ('com.example.Other', 'public interface Other extends Comparable<Other>'),
    ('com.example.Base', 'public class Base'),
    ('com.example.Color', 'public enum Color implements Other'),
    ('com.example.Marker', 'public @interface Marker'),
])
def test_signature(app, node_id, text):
    assert signatures(app)[node_id] == text


@pytest.mark.parametrize('node_id, text', [
    ('com.example.Box.getName()', 'String getName()'),
    ('com.example.Box.counts', 'List<? extends Number> counts'),
])
def test_signature_without_modifiers(app, node_id, text):
    assert signatures(app)[node_id] == text


def test_references(app):
    refs = references(app)
    assert refs['Box'] == 'com.example.Box'
    assert refs['Box.wrap'] == 'com.example.Box.wrap(U[], String)'
    assert refs['getName'] == 'com.example.Box.getName()'
    assert refs['Box.SIZE'] == 'com.example.Box.SIZE'
    assert refs['String'] == 'http://docs.oracle.com/javase/8/docs/api/java/lang/String.html'
    assert refs['java.util.List'] == 'http://docs.oracle.com/javase/8/docs/api/java/util/List.html'


def test_signature_references(app):
    doctree = resolved_doctree(app)
    node = next(node for node in doctree.findall(addnodes.desc_signature) if 'com.example.Box' in node['ids'])
    refs = {ref.astext(): ref.get('refid') or ref.get('refuri') for ref in node.findall(lambda n: 'refuri' in n
                                                                                          or 'refid' in n)}
    assert refs['Base'] == 'com.example.Base'
    assert refs['Other'] == 'com.example.Other'
    assert refs['Serializable'] == 'http://docs.oracle.com/javase/8/docs/api/java/io/Serializable.html'


def test_imported_type(build):
    app = build('.. java:import:: java.util List\n\n.. java:method:: List get()\n   :outertype: Foo\n')
    doctree = resolved_doctree(app)
    refs = {ref.astext(): ref['refuri'] for ref in doctree.findall(lambda n: 'refuri' in n)}
    assert refs['List'] == 'http://docs.oracle.com/javase/8/docs/api/java/util/List.html'


def test_index_entries(app):
    entries = [entry[1] for node in resolved_doctree(app).findall(addnodes.index) for entry in node['entries']]
    assert entries == [
        'com.example (package)', 'Box (Java class)', 'Box(T) (Java constructor)',
        'wrap(U[], String) (Java method)', 'getName() (Java method)', 'setName(String) (Java method)',
        'SIZE (Java field)', 'counts (Java field)', 'Other (Java interface)', 'Base (Java class)',
        'Color (Java enum)', 'Marker (Java annotation)',
    ]


def test_cross_page_reference(build):
    app = build(':java:type:`com.example.Box`', pages={
        'other': '.. java:package:: com.example\n\n.. java:type:: public class Box\n',
    }, master_doc='index', exclude_patterns=[], suppress_warnings=['toc.not_included'])
    assert references(app) == {'com.example.Box': 'other.html#com.example.Box'}


def test_package_reference(build):
    app = build(':java:package:`com.example`', pages={
        'other': '.. java:package:: com.example\n',
    }, suppress_warnings=['toc.not_included'])
    assert references(app) == {'com.example': 'other.html#package-com.example'}


@pytest.mark.parametrize('parallel', [0, 2])
def test_package_on_several_pages(build, parallel):
    pages = {f'page{i}': '.. java:package:: com.example\n' for i in range(4)}
    app = build(':java:package:`com.example`', pages=pages, parallel=parallel,
                suppress_warnings=['toc.not_included'])
    assert references(app) == {'com.example': 'page0.html#package-com.example'}


def test_package_no_index(build):
    app = build(':java:package:`com.example`', pages={
        'other': '.. java:package:: com.example\n   :no-index:\n',
    }, suppress_warnings=['toc.not_included'])
    assert references(app) == {}
    assert any('reference target not found: com.example' in line for line in warnings(app))


@pytest.mark.xfail(reason='the any role finds an object once for each role')
def test_any_reference(build):
    app = build('.. java:package:: com.example\n\n.. java:type:: public class Box\n\n:any:`Box`\n')
    assert warnings(app) == []
    assert references(app) == {'Box': 'com.example.Box'}


def test_duplicate_warning(build):
    app = build('.. java:type:: public class Box\n', pages={'other': '.. java:type:: public class Box\n'},
                suppress_warnings=['toc.not_included'])
    assert any('duplicate object description of Box' in line for line in warnings(app))


@pytest.mark.parametrize('directive, sig, message', [
    ('method', 'int (', 'syntax error in method signature'),
    ('method', 'int x', 'expected method declaration'),
    ('constructor', 'Foo(', 'syntax error in constructor signature'),
    ('field', 'int x(', 'syntax error in field signature'),
    ('field', 'int x()', 'expected field declaration'),
])
def test_invalid_signature(build, directive, sig, message):
    app = build(f'.. java:{directive}:: {sig}\n   :outertype: Foo\n')
    assert any(message in line for line in warnings(app))


@pytest.mark.xfail(reason='a type signature error says field')
def test_invalid_type_signature(build):
    app = build('.. java:type:: class {\n')
    assert any('syntax error in type signature' in line for line in warnings(app))


@pytest.mark.xfail(reason='documenting several fields at once is not an error')
def test_several_fields(build):
    app = build('.. java:field:: int x, y\n   :outertype: Foo\n')
    assert any('only one field may be documented at a time' in line for line in warnings(app))


def test_parallel_build(build):
    pages = {f'page{i}': f'.. java:package:: com.example\n   :no-index:\n\n.. java:type:: public class C{i}\n'
             for i in range(4)}
    app = build(':java:type:`C0` :java:type:`C3`', pages=pages, parallel=2,
                suppress_warnings=['toc.not_included'])
    assert references(app) == {'C0': 'page0.html#com.example.C0', 'C3': 'page3.html#com.example.C3'}
