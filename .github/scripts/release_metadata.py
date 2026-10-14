"""Validate release metadata without network access or credentials."""
import json
import os
from pathlib import Path
import re
import sys


def metadata(root, requested_tag=None):
    version = json.loads((root / 'custom_components/bord_gais_energy/manifest.json').read_text())['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?', version):
        raise ValueError('Unsupported release version')
    tag = 'v' + version
    if requested_tag and requested_tag != tag:
        raise ValueError('Tag does not match manifest version')
    changelog = (root / 'CHANGELOG.md').read_text()
    section = re.search(r'^## ' + re.escape(version) + r'\s*\n(.*?)(?=^## |\Z)', changelog, re.M | re.S)
    if not section or not section.group(1).strip():
        raise ValueError('Missing release notes')
    return {'version':version, 'tag':tag, 'prerelease':str('-' in version).lower()}, section.group(1).strip() + '\n'


if __name__ == '__main__':
    requested = os.environ.get('RELEASE_TAG') or None
    values, notes = metadata(Path('.'), requested)
    Path(os.environ.get('NOTES_FILE', 'release-notes.md')).write_text(notes)
    if output := os.environ.get('GITHUB_OUTPUT'):
        with open(output, 'a') as handle:
            for key, value in values.items():
                handle.write(f'{key}={value}\n')
    print('Validated release ' + values['tag'])
