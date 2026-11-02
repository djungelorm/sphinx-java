""" Write sphinx_java/javase.py from the element lists and java.lang package summaries of the Java SE docs """

import argparse
import itertools
import re
import urllib.request
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / 'sphinx_java' / 'javase.py'
API = 'https://docs.oracle.com/en/java/javase/{}/docs/api/'
PREFIXES = ('java.', 'javax.', 'org.ietf.', 'org.w3c.', 'org.xml.')


def fetch(url: str) -> str:
    with urllib.request.urlopen(url) as response:
        text: str = response.read().decode()
        return text


def modules(version: int) -> dict[str, str]:
    """ The module of each package in one Java version """
    result = {}
    module = ''
    for line in fetch(API.format(version) + 'element-list').split():
        if line.startswith('module:'):
            module = line.removeprefix('module:')
        elif line.startswith(PREFIXES):
            result[line] = module
    return result


def java_lang_types(version: int) -> set[str]:
    """ The top-level types in java.lang in one Java version """
    summary = fetch(API.format(version) + 'java.base/java/lang/package-summary.html')
    return set(re.findall(r'href="([A-Z][A-Za-z0-9]*)\.html"', summary))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('versions', nargs='+', type=int, help='the Java versions, such as 11 17 21 25')
    versions = parser.parse_args().versions

    packages: dict[str, str] = {}
    types: set[str] = set()
    for version in versions:
        for package, module in modules(version).items():
            if packages.setdefault(package, module) != module:
                raise SystemExit(f'{package} is in {packages[package]} and {module}')
        types |= java_lang_types(version)

    # The license header of the existing file
    lines = [*itertools.takewhile(lambda line: line.startswith('#'), OUTPUT.read_text().splitlines()), '']
    lines += [f'""" Java SE {", ".join(map(str, versions))} names, from scripts/javase.py """', '',
             '# The module of each package', 'JAVA_SE_MODULES = {']
    lines += [f"    '{package}': '{packages[package]}'," for package in sorted(packages)]
    lines += ['}', '', '# The top-level types in java.lang', 'JAVA_LANG_TYPES = frozenset({']
    lines += [f"    '{name}'," for name in sorted(types)]
    lines += ['})', '']
    OUTPUT.write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
