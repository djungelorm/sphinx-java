""" Write sphinx_java/javase_modules.py from the element lists of the Java SE docs """

import argparse
import urllib.request
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / 'sphinx_java' / 'javase_modules.py'
ELEMENT_LIST = 'https://docs.oracle.com/en/java/javase/{}/docs/api/element-list'
PREFIXES = ('java.', 'javax.', 'org.ietf.', 'org.w3c.', 'org.xml.')


def modules(version: int) -> dict[str, str]:
    """ The module of each package in one Java version """
    with urllib.request.urlopen(ELEMENT_LIST.format(version)) as response:
        lines = response.read().decode().split()
    result = {}
    module = ''
    for line in lines:
        if line.startswith('module:'):
            module = line.removeprefix('module:')
        elif line.startswith(PREFIXES):
            result[line] = module
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('versions', nargs='+', type=int, help='the Java versions, such as 11 17 21 25')
    versions = parser.parse_args().versions

    packages: dict[str, str] = {}
    for version in versions:
        for package, module in modules(version).items():
            if packages.setdefault(package, module) != module:
                raise SystemExit(f'{package} is in {packages[package]} and {module}')

    lines = [f'""" The module of each package in the Java SE {", ".join(map(str, versions))} docs, '
             'from scripts/javase_modules.py """', '', 'JAVA_SE_MODULES = {']
    lines += [f"    '{package}': '{packages[package]}'," for package in sorted(packages)]
    lines += ['}', '']
    OUTPUT.write_text('\n'.join(lines))


if __name__ == '__main__':
    main()
