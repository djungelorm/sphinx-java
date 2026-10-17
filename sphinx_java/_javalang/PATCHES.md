# Changes to javalang 0.13.1

The parser is vendored from javalang 0.13.1, without its Javadoc parser. These changes add the Java syntax that signatures need. Each changed place in the code has a `# sphinx-java:` comment.

- Records: `record` declarations with components, and compact constructors.
- Sealed classes: the `sealed` and `non-sealed` modifiers, and `permits` clauses.
