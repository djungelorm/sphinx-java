# CLAUDE.md

## Overview

sphinx-java is a Sphinx extension that adds a `java` domain for documenting Java APIs. Users enable it with `extensions = ['sphinx_java']` in their `conf.py`. It is a fork of javasphinx 0.9.16 without `javasphinx-apidoc`, and keeps the javasphinx directive, role and config names so existing docs keep working.

Supported targets: Python 3.11 and later, Sphinx 7.2 and later. The hatch test environments cover every Python from 3.11 to 3.15, and each Sphinx minor version from 7.2 to 9.1.

## Commands

```bash
hatch run lint:check                   # ruff on sphinx_java, tests and scripts
hatch run types:check                  # mypy in strict mode on sphinx_java
hatch run matrix:all                   # pytest with coverage in every test environment, in parallel
hatch run matrix:all --python 3.14     # every test environment for one Python
hatch run test.py3.14-9.1:all -k extdoc   # selected tests in one environment
hatch build                            # build sdist and wheel into dist/
```

The tests are in `tests` and run with pytest:

- `test_render.py`: builds small projects with Sphinx's test fixtures and checks rendered signature text, warnings and where cross-references point.
- `test_extdoc.py`: the external Javadoc URLs and the `java:extdoc` role.
- `test_projects.py`: builds `tests/roots/test-basic` in nitpicky mode and fails on any warning.

Warnings fail the tests. Known bugs have tests marked `xfail`, and `xfail_strict` is on. A fix makes its test pass, which fails the run until the marker is removed. Coverage of `sphinx_java` must be 100%.

To check a new feature, add rendering checks to `tests/test_render.py` and a directive using it to `tests/roots/test-basic/index.rst`.

## Architecture

- **`__init__.py`**: `setup()` registers the domain, the `javadoc_url_map` and `javadoc_java_se_version` config values and the `java:extdoc` role. It connects `check_config` to `config-inited` and `suppress_missing_reference` to `warn-missing-reference`.
- **Signature parsing** (`syntax.py`): tree-sitter-java parses each signature wrapped in a minimal compilation unit, such as `class _ { sig; }` for a method. `syntax.py` turns the tree into a typed model of the declaration, with initializers and annotation arguments as written. A signature with a syntax error, or more than one declaration, raises `JavaSyntaxError`.
- **Directives** (`domain.py`): `JavaObject` (an `ObjectDescription` subclass) is the base for `type`, `method`, `constructor`, `field` and `enumconstant`. Each subclass implements `handle_signature`, which parses the signature and returns the name. Methods and constructors are named with their parameter types, such as `wrap(U[], String)`. `_build_type_node` emits a `pending_xref` for each referenced type. `package` and `import` are plain directives.
- **Scoping**: `env.ref_context` holds `java:package`, the `java:outertype` stack, the `java:typeparams` stack and the `java:imports` map. `before_content` and `after_content` push and pop the stacks for nested directives.
- **Cross-references**: `_note_context` stores the package, type and import on each reference, from `JavaXRefRole.process_link` or `JavaDomain.process_field_xref`. It marks type parameters and primitive types `java:plain`, which never resolve and never warn. The package of a qualified name is marked `java:nowarn`. `JavaDomain.find_object` tries the target as written, then prefixed with the package and type, then by suffix. `external_ref` falls back to the external docs. Node ids are the full names, and a package's id is `package-` and its name.
- **External links** (`extdoc.py`): `get_javadoc_ref` builds a URL from the longest matching package in `javadoc_url_map`, merged with the Java SE defaults. The Java SE docs from Java 11 put module names in the paths. `javase.py` maps each Java SE package to its module and lists the `java.lang` types. `python scripts/javase.py 11 17 21 25` regenerates it from the Javadoc.
- **Parallel builds**: `setup()` declares the extension parallel safe, and `merge_domaindata` merges the objects from parallel reads. A package on several pages is recorded for the first page by name, so the target is the same in serial and parallel builds.

## Conventions

- Use `_()` from `sphinx.locale` for translatable strings, and `__()` for log messages.
- Code must pass `hatch run lint:check` and `hatch run types:check`. The ruff and mypy settings are in `pyproject.toml`.
- Annotate all functions in `sphinx_java`. The package ships `py.typed`.
- The javasphinx files keep their Apache license header. Releases bump the version in `pyproject.toml` and add an entry to `CHANGES.txt`.

## Writing

Applies to anything a person reads: commit messages, PR descriptions, code comments, docs.

General guidance:

 * Write concisely. When trimming, keep facts and trim the framing.
 * Keep descriptions high level. The code is the detail, and should be self-documenting.
 * One person writes it and many may read it. You, the writer, should do the compression.
 * Avoid emdashes. Use a comma or a hyphen instead.
 * Avoid AI tells: "emojis", greetings etc.
 * American English everywhere ("meters", "color", "normalized").
 * No "Authored by" / `Co-Authored-By` lines.

### Sentences

Average 14 words per sentence and under half a comma. Long comma-chained sentences are the main
way writing here goes wrong.

 * **One idea per sentence, two clauses at most.** A fact and its consequence make a sentence.
   Never chain with `, so ..., and ...` or `, which ..., so ...`.
 * **Say what a thing is, not what it is not.** Negate only to correct a misreading the reader is
   likely to arrive with, and only attached to a positive statement. "rather than", "no longer",
   "nothing" and "not a" are the tells.
 * **Name the thing.** No "the thing", "nothing", "whatever", "anything". The subject of a
   sentence is a definite noun.
 * **No anthropomorphism.** Sphinx and the parser do not say, ask, see, hear or refuse,
   and are never finished with anything. State the mechanism.
 * **No setup and payoff, and no editorializing.** A sentence that only frames the next one is cut.
 * **Paragraphs run one to three sentences**, about 30 words. Past four it is two paragraphs, or a
   list.

### Documentation

 * **Lead with the example.** The unit of explanation is one or two sentences of setup ending in a
   colon, then the code, then any explanation of it. A section that explains a feature without
   showing it is the wrong shape.
 * **Address the reader** as "you". Do not write about an abstract "a user" or "a project".
 * Reuse the stock forms already in the docs.
 * Headings are short Title Case noun phrases, not clauses with verbs.
 * `.. note::` in block form with a one or two sentence body for a caveat, `.. seealso::` for a
   cross-reference. Never hang a paragraph off an inline `.. note::`.
 * Say what something does. Why it is implemented that way belongs in the code.

### Code comments

Comments carry the constraint the code itself cannot.

 * **Size the comment to the code it describes.** A line or two of code gets a fragment naming the
   step, a method a sentence, a file or a mechanism not recoverable from the code a paragraph. A
   paragraph over a one-line statement is the usual failure.
 * **The default form is a label**: a fragment above the lines it covers, sentence case, no
   trailing period. A long method is often a run of these.
 * **Comment the surprise**: a Sphinx or Javadoc quirk, a workaround, an ordering constraint, a unit, a sign
   convention. Code that reads plainly gets no comment, and never one that restates the line below.
 * **State the constraint, do not argue the alternative.** A comment that proves a case, or names
   what would break, is arguing.
 * **Never reference what a change replaced.** A comment explains the code as it stands, to someone
   who never saw the old version. How a value was arrived at belongs in the commit message and the
   PR, though a measurement that sizes a constant is part of what it means.
 * **Name the thing, and use "we".** Openers are "The ...", "Whether ..." and a verb, as in the
   docstrings. Do not nominalize to avoid the first person.
 * **Write what the code names.** ASCII only, and no symbol that appears nowhere in the source.
   `--` is an emdash by another spelling. American English, as everywhere else.
 * **One comment per place.** Do not clone a comment across sibling files with the noun swapped.
 * `# Note:` prefixes a one-sentence caveat attached to the line below. It is the only marker in
   use, and an open question is a GitHub issue.
 * Trailing comments are rare and short, and are not padded into aligned columns. Do not split a
   comment into paragraphs, or mark up `*emphasis*`.
 * The **Sentences** rules apply in full. Anthropomorphism is the one comments break most.

## Commits

 * One logical thing per commit.
 * Concise message, sized to the diff. Tiny commits just need a single-line summary, larger commits needs
   a single-line summary then short paragraph(s).

## Before pushing

Run the full suite locally before pushing a branch:

```bash
hatch run lint:check
hatch run types:check
hatch run matrix:all
```

`matrix:all` runs the tests in every test environment, several at once, and writes a log for each to `test-output`. Hatch fetches any Python it cannot find. Push only when all three commands pass. If a Python version is unavailable locally, say so rather than skip it silently.

## Pull requests

 * Concise technical prose, proportional to the diff; bullets only for discrete items. Multi-part
   change → lead paragraphs with a short bold phrase (`**Root cause.**`, `**Fix.**`, `**Testing.**`).
 * State the problem, the change, and for a fix how it was verified.
 * Do not state that tests CI covers would pass (like `bazel test //:test`).
 * Do not repeat implementation details that are clear from the commit messages.
 * After drafting, cut: any sentence that restates the diff, the weaker of two sections that say the
   same thing, any paragraph over four lines. If it will not compress further, that is a sign the
   change is not understood well enough yet; re-read the diff rather than add words.
 * End with one or more `Fixes #NNN` when open issues are fixed by the PR; omit otherwise.
 * End with one or more `Related to #NNN` when open issues are related to but not fixed by the PR;
   omit otherwise.
 * **No AI-attribution or "Generated with" footer**, in PR bodies and commit messages alike.
 * One paragraph per line; GitHub renders single newlines literally. Reflow wrapped text.
