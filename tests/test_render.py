import pytest
from conftest import references, resolved_doctree, signatures, warnings
from docutils import nodes
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


def test_type_parameters(build):
    app = build('''
.. java:type:: public class Box<T> extends Base<T>

   .. java:method:: public <U> T convert(U value, List<T> items)

      :param U value: The value.
      :param T[] items: The items.

   .. java:constructor:: public <V> Box(V value)

.. java:method:: T outside()
   :outertype: Other
''')
    assert [line for line in warnings(app) if 'not found' in line] == [
        f'{app.srcdir / "index.rst"}:2: WARNING: java:type reference target not found: Base',
        f'{app.srcdir / "index.rst"}:4: WARNING: java:type reference target not found: List',
        f'{app.srcdir / "index.rst"}:11: WARNING: java:type reference target not found: T',
    ]
    assert signatures(app)['Box.convert(U, List)'] == 'public <U> T convert(U value, List<T> items)'
    assert signatures(app)['Box.Box(V)'] == 'public <V> Box(V value)'


def test_primitive_types_in_fields(build):
    app = build('''
.. java:method:: long get(int a, byte[] b, double... c)
   :outertype: Foo

   :param int a: A.
   :param byte[] b: B.
   :param double... c: C.
''')
    assert warnings(app) == []


def test_qualified_names(build):
    app = build('''
.. java:package:: com.example

.. java:type:: public class Box

.. java:method:: java.util.List<com.example.Box> get(org.other.Thing thing)
   :outertype: Other
''')
    assert warnings(app) == [
        f'{app.srcdir / "index.rst"}:6: WARNING: java:type reference target not found: org.other.Thing',
    ]
    doctree = resolved_doctree(app)
    node = list(doctree.findall(addnodes.desc_signature))[-1]
    refs = [(ref.astext(), ref.get('refid') or ref.get('refuri'))
            for ref in node.findall(lambda n: 'refuri' in n or 'refid' in n)]
    assert refs == [
        ('java.util', 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/package-summary.html'),
        ('List', 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html'),
        ('com.example', 'package-com.example'),
        ('Box', 'com.example.Box'),
    ]


def test_references(app):
    refs = references(app)
    assert refs['Box'] == 'com.example.Box'
    assert refs['Box.wrap'] == 'com.example.Box.wrap(U[], String)'
    assert refs['getName'] == 'com.example.Box.getName()'
    assert refs['Box.SIZE'] == 'com.example.Box.SIZE'
    assert refs['String'] == 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html'
    assert refs['java.util.List'] == 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html'


def test_signature_references(app):
    doctree = resolved_doctree(app)
    node = next(node for node in doctree.findall(addnodes.desc_signature) if 'com.example.Box' in node['ids'])
    refs = {ref.astext(): ref.get('refid') or ref.get('refuri') for ref in node.findall(lambda n: 'refuri' in n
                                                                                          or 'refid' in n)}
    assert refs['Comparable'] == 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Comparable.html'
    assert refs['Base'] == 'com.example.Base'
    assert refs['Other'] == 'com.example.Other'
    assert refs['Serializable'] == 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/io/Serializable.html'


def test_imported_type(build):
    app = build('.. java:import:: java.util List\n\n.. java:method:: List get()\n   :outertype: Foo\n')
    doctree = resolved_doctree(app)
    refs = {ref.astext(): ref['refuri'] for ref in doctree.findall(lambda n: 'refuri' in n)}
    assert refs['List'] == 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html'


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
    pages = {f'page{i}': '.. java:package:: com.example\n' for i in range(8)}
    app = build(':java:package:`com.example`', pages=pages, parallel=parallel,
                suppress_warnings=['toc.not_included'])
    assert references(app) == {'com.example': 'page0.html#package-com.example'}


def test_package_no_index(build):
    app = build(':java:package:`com.example`', pages={
        'other': '.. java:package:: com.example\n   :no-index:\n',
    }, suppress_warnings=['toc.not_included'])
    assert references(app) == {}
    assert any('reference target not found: com.example' in line for line in warnings(app))


def test_any_reference(build):
    app = build('.. java:package:: com.example\n\n.. java:type:: public class Box\n\n:any:`Box`\n')
    assert warnings(app) == []
    assert references(app) == {'Box': 'com.example.Box'}


def test_any_reference_external(build):
    app = build(':any:`String`')
    assert warnings(app) == []
    assert references(app) == {'String': 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html'}


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
    ('field', 'String x = "a', 'syntax error in field signature'),
    ('constructor', 'String A =', 'syntax error in constructor signature'),
])
def test_invalid_signature(build, directive, sig, message):
    app = build(f'.. java:{directive}:: {sig}\n   :outertype: Foo\n')
    assert any(message in line for line in warnings(app))


def test_invalid_type_signature(build):
    app = build('.. java:type:: class {\n')
    assert any('syntax error in type signature' in line for line in warnings(app))


def test_several_fields(build):
    app = build('.. java:field:: int x, y\n   :outertype: Foo\n')
    assert any('only one field may be documented at a time' in line for line in warnings(app))


def test_parallel_build(build):
    pages = {f'page{i}': f'.. java:package:: com.example\n   :no-index:\n\n.. java:type:: public class C{i}\n'
             for i in range(8)}
    app = build(':java:type:`C0` :java:type:`C3`', pages=pages, parallel=2,
                suppress_warnings=['toc.not_included'])
    assert references(app) == {'C0': 'page0.html#com.example.C0', 'C3': 'page3.html#com.example.C3'}


@pytest.mark.parametrize('sig, node_id, text', [
    ('java.util.Map.Entry<String, Integer> first()', 'Foo.first()', 'java.util.Map.Entry<String, Integer> first()'),
    ('Map<String, Integer>.Entry first()', 'Foo.first()', 'Map<String, Integer>.Entry first()'),
    ('String[][] grid(List<?> items)', 'Foo.grid(List)', 'String[][] grid(List<?> items)'),
    ('default void run()', 'Foo.run()', 'default void run()'),
    ('public default void run()', 'Foo.run()', 'public default void run()'),
    ('<T extends List<?>> void wildcard(T items)', 'Foo.wildcard(T)', '<T extends List<?>> void wildcard(T items)'),
    ('<T extends Number & Comparable<? super T>> T max()', 'Foo.max()',
     '<T extends Number & Comparable<? super T>> T max()'),
])
def test_method_types(build, sig, node_id, text):
    app = build(f'.. java:method:: {sig}\n   :outertype: Foo\n', nitpicky=False)
    assert warnings(app) == []
    assert signatures(app)[node_id] == text


@pytest.mark.parametrize('sig, text', [
    ('interface Plain', 'interface Plain'),
    ('enum Plain', 'enum Plain'),
    ('class Plain<T>', 'class Plain<T>'),
])
def test_type_without_supertypes(build, sig, text):
    app = build(f'.. java:type:: {sig}\n')
    assert warnings(app) == []
    assert signatures(app)['Plain'] == text


def test_constructor_signature_is_not_a_method(build):
    app = build('.. java:constructor:: int foo()\n   :outertype: Foo\n')
    assert any('expected constructor declaration' in line for line in warnings(app))


def test_same_page_duplicate(build):
    app = build('.. java:type:: public class Box\n\n.. java:type:: public class Box\n')
    assert warnings(app) == []
    assert [node['ids'] for node in resolved_doctree(app).findall(addnodes.desc_signature)] == [['Box'], []]


def test_tilde_without_package(build):
    app = build('.. java:type:: public class Box\n\n:java:type:`~Box`\n')
    assert references(app) == {'Box': 'Box'}


def test_any_reference_unresolved(build):
    app = build(':any:`Missing`')
    assert any("'any' reference target not found: Missing" in line for line in warnings(app))


def test_field_xref_without_inliner(build):
    app = build('.. java:type:: public class Box<T>\n\n   .. java:import:: java.util List\n')
    domain = app.env.get_domain('java')
    app.env.ref_context['java:typeparams'] = [frozenset({'T'})]
    app.env.ref_context['java:imports'] = {'List': 'java.util'}
    node = addnodes.pending_xref('', reftarget='T')
    domain.process_field_xref(node)
    assert node['java:plain']
    node = addnodes.pending_xref('', reftarget='List')
    domain.process_field_xref(node)
    assert node['java:package'] == 'java.util'
    assert node['java:imported']


def test_rebuild_after_removing_a_page(build, make_app):
    app = build(':java:type:`com.example.Box`', pages={
        'other': '.. java:package:: com.example\n\n.. java:type:: public class Box\n',
    }, suppress_warnings=['toc.not_included'])
    assert references(app) == {'com.example.Box': 'other.html#com.example.Box'}
    (app.srcdir / 'other.rst').unlink()
    app = make_app('html', srcdir=app.srcdir, confoverrides={'nitpicky': True})
    app.build()
    assert 'com.example.Box' not in app.env.get_domain('java').objects
    assert any('reference target not found: com.example.Box' in line for line in warnings(app))


def test_generic_types_in_fields(build):
    app = build('''
.. java:method:: void move(org.javatuples.Triplet<Double, Double, Double> position, java.util.List<String> names)
   :outertype: Foo

   :param org.javatuples.Triplet<Double,Double,Double> position: The position.
   :param java.util.List<String> names: The names.
''', javadoc_url_map={'org.javatuples': ('https://www.javatuples.org/apidocs/', 'javadoc')})
    assert warnings(app) == []
    fields = next(resolved_doctree(app).findall(nodes.field_list))
    assert {ref.astext(): ref['refuri'] for ref in fields.findall(nodes.reference)} == {
        'org.javatuples.Triplet<Double,Double,Double>': 'https://www.javatuples.org/apidocs/org/javatuples/Triplet.html',
        'java.util.List<String>': 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html',
    }


@pytest.mark.parametrize('rst, text, target', [
    (':java:type:`List<String>`', 'List<String>', 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html'),
    (':java:type:`~java.util.List<String>`', 'List', 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html'),
    (':java:type:`the list <java.util.List>`', 'the list',
     'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html'),
])
def test_generic_type_reference(build, rst, text, target):
    app = build('.. java:import:: java.util List\n\n' + rst)
    assert warnings(app) == []
    assert references(app) == {text: target}



API = 'https://docs.oracle.com/en/java/javase/25/docs/api/java.base/'


@pytest.mark.parametrize('directive, sig, node_id, text, refs', [
    ('method', 'void read() throws IOException', 'Foo.read()', 'void read() throws IOException',
     {'IOException': API + 'java/io/IOException.html'}),
    ('method', 'void read() throws java.io.IOException, Error', 'Foo.read()',
     'void read() throws java.io.IOException, Error',
     {'java.io': API + 'java/io/package-summary.html', 'IOException': API + 'java/io/IOException.html',
      'Error': API + 'java/lang/Error.html'}),
    ('method', '<E extends Exception> void run() throws E', 'Foo.run()', '<E extends Exception> void run() throws E',
     {'Exception': API + 'java/lang/Exception.html'}),
    ('constructor', 'public Foo(String path) throws IOException', 'Foo.Foo(String)',
     'public Foo(String path) throws IOException',
     {'String': API + 'java/lang/String.html', 'IOException': API + 'java/io/IOException.html'}),
])
def test_throws(build, directive, sig, node_id, text, refs):
    app = build(f'.. java:import:: java.io IOException\n\n.. java:{directive}:: {sig}\n   :outertype: Foo\n')
    assert warnings(app) == []
    assert signatures(app)[node_id] == text
    node = next(resolved_doctree(app).findall(addnodes.desc_signature))
    assert {ref.astext(): ref['refuri'] for ref in node.findall(lambda n: 'refuri' in n)} == refs


@pytest.mark.parametrize('directive, sig', [('method', 'void read()'), ('constructor', 'Foo()')])
def test_throws_field(build, directive, sig):
    app = build(f'''
.. java:import:: java.io IOException

.. java:{directive}:: {sig}
   :outertype: Foo

   :throws IOException: If the read fails.
''')
    assert warnings(app) == []
    fields = next(resolved_doctree(app).findall(nodes.field_list))
    assert {ref.astext(): ref['refuri'] for ref in fields.findall(nodes.reference)} == {
        'IOException': API + 'java/io/IOException.html',
    }


def test_type_parameter_bounds(build):
    app = build('''
.. java:type:: public class Base

.. java:method:: <K, T extends Base & Comparable<? super T>> T max(K key, T a, T b)
   :outertype: Base
''')
    assert warnings(app) == []
    node = list(resolved_doctree(app).findall(addnodes.desc_signature))[-1]
    assert node.astext() == '<K, T extends Base & Comparable<? super T>> T max(K key, T a, T b)'
    refs = [(ref.astext(), ref.get('refid') or ref.get('refuri'))
            for ref in node.findall(lambda n: 'refuri' in n or 'refid' in n)]
    assert refs == [('Base', 'Base'), ('Comparable', API + 'java/lang/Comparable.html')]


def test_constructor_type_parameter_bounds(build):
    app = build('.. java:constructor:: public <N extends Number> Box(N value)\n   :outertype: Box\n')
    assert warnings(app) == []
    assert signatures(app)['Box.Box(N)'] == 'public <N extends Number> Box(N value)'
    node = next(resolved_doctree(app).findall(addnodes.desc_signature))
    assert {ref.astext(): ref['refuri'] for ref in node.findall(lambda n: 'refuri' in n)} == {
        'Number': API + 'java/lang/Number.html',
    }


@pytest.mark.parametrize('sig, text', [
    ('int A = -1', 'int A = -1'),
    ('int A = 1 << 3', 'int A = 1 << 3'),
    ('int A = Integer.MAX_VALUE', 'int A = Integer.MAX_VALUE'),
    ('List<String> A = new ArrayList<>()', 'List<String> A = new ArrayList<>()'),
    ('String A = "a = b";', 'String A = "a = b"'),
    ('int[] A = {1, 2}', 'int[] A = {1, 2}'),
    ('@Size(max = 1) int A = 2', '@Size(max = 1) int A = 2'),
])
def test_field_initializer(build, sig, text):
    app = build(f'.. java:field:: {sig}\n   :outertype: Foo\n', nitpicky=False)
    assert warnings(app) == []
    assert signatures(app)['Foo.A'] == text


@pytest.mark.parametrize('directive, sig, node_id, text', [
    ('type', '@Deprecated public class A', 'A', None),
    ('type', '@SuppressWarnings("unchecked") public class A', 'A', None),
    ('type', '@Retention(RetentionPolicy.RUNTIME) public @interface A', 'A', None),
    ('method', '@Override public String toString()', 'Foo.toString()', None),
    ('method', 'public @Deprecated void a()', 'Foo.a()', '@Deprecated public void a()'),
    ('method', '@java.lang.Deprecated(since = "9", forRemoval = true) void a()', 'Foo.a()', None),
    ('method', '@A @B({1, 2}) void a()', 'Foo.a()', None),
    ('method', 'void a(@Nullable final String x, int y)', 'Foo.a(String, int)', None),
    ('method', 'void a(final @Nullable String x)', 'Foo.a(String)', 'void a(@Nullable final String x)'),
    ('method', 'void a(final int... xs)', 'Foo.a(int)', None),
    ('constructor', '@Inject public Foo(Bar bar)', 'Foo.Foo(Bar)', None),
    ('field', '@Deprecated public int a', 'Foo.a', None),
])
def test_annotations(build, directive, sig, node_id, text):
    outertype = '' if directive == 'type' else '\n   :outertype: Foo'
    app = build(f'.. java:{directive}:: {sig}{outertype}\n', nitpicky=False)
    assert warnings(app) == []
    assert signatures(app)[node_id] == (text or sig)


def test_annotation_links(build):
    app = build('.. java:method:: @Deprecated @java.lang.FunctionalInterface void a()\n   :outertype: Foo\n')
    assert warnings(app) == []
    node = next(resolved_doctree(app).findall(addnodes.desc_signature))
    assert {ref.astext(): ref['refuri'] for ref in node.findall(lambda n: 'refuri' in n)} == {
        'Deprecated': API + 'java/lang/Deprecated.html',
        'java.lang': API + 'java/lang/package-summary.html',
        'FunctionalInterface': API + 'java/lang/FunctionalInterface.html',
    }


ENUM_SOURCE = '''
.. java:package:: com.example

.. java:type:: public enum Color

   .. java:enumconstant:: RED

   .. java:enumconstant:: @Deprecated GREEN(0x00FF00, "green")

   .. java:enumconstant:: @Shade(dark = true) BLUE("(blue)")

:java:field:`Color.RED`, :java:ref:`Color.GREEN`, :any:`Color.BLUE`
'''


@pytest.mark.parametrize('node_id, text', [
    ('com.example.Color.RED', 'RED'),
    ('com.example.Color.GREEN', '@Deprecated GREEN(0x00FF00, "green")'),
    ('com.example.Color.BLUE', '@Shade(dark = true) BLUE("(blue)")'),
])
def test_enum_constant(build, node_id, text):
    app = build(ENUM_SOURCE, nitpicky=False)
    assert warnings(app) == []
    assert signatures(app)[node_id] == text


def test_enum_constant_references(build):
    app = build(ENUM_SOURCE, nitpicky=False)
    assert references(app) == {
        'Deprecated': API + 'java/lang/Deprecated.html',
        'Color.RED': 'com.example.Color.RED',
        'Color.GREEN': 'com.example.Color.GREEN',
        'Color.BLUE': 'com.example.Color.BLUE',
    }
    entries = [entry[1] for node in resolved_doctree(app).findall(addnodes.index) for entry in node['entries']]
    assert 'RED (Java enum constant)' in entries


@pytest.mark.parametrize('sig', ['RED extra', 'RED(', '1'])
def test_invalid_enum_constant(build, sig):
    app = build(f'.. java:enumconstant:: {sig}\n   :outertype: Color\n')
    assert any('syntax error in enum constant signature' in line for line in warnings(app))
