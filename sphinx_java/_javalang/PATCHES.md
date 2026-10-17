# Changes to javalang 0.13.1

The parser is vendored from javalang 0.13.1, without its Javadoc parser. These changes add the Java syntax that signatures need. Each changed place in the code has a `# sphinx-java:` comment.

- Records: `record` declarations with components, and compact constructors.
- Sealed classes: the `sealed` and `non-sealed` modifiers, and `permits` clauses.
- Type annotations: on type names and their parts, type arguments and wildcards, array dimensions, varargs and type parameters. Each array dimension holds a list of annotations, or None.
- Receiver parameters: `this` and `Outer.this` as parameter names.
- Annotation elements: a `default` value after the parameters of a method.
- Tokenizer: a `0` at the end of the input is a decimal integer.
- Backtracking: popping a nested marker without a reset left the outer marker at the nested position.
