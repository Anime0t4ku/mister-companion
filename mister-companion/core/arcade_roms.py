from pathlib import Path
import re
import xml.etree.ElementTree as ET


def mra_requirements(data):
    root = ET.fromstring(data)
    groups = set()
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1].lower() != 'rom':
            continue
        names = []
        for value in element.get('zip', '').split('|'):
            value = value.strip()
            if not value:
                continue
            if not re.fullmatch(r'[\w .()+\-]+(?:\.zip)?', value, re.ASCII) or value in {'.', '..'}:
                raise ValueError(f'Unsafe ROM ZIP name: {value}')
            name = value if value.lower().endswith('.zip') else value + '.zip'
            names.append(name.lower())
        if names:
            groups.add(tuple(sorted(set(names))))
    return sorted(groups)


def local_zip_index(folder, recursive=False, cancelled=lambda: False):
    root = Path(folder)
    if not root.is_dir():
        raise ValueError(f'Folder does not exist: {folder}')
    result = {}
    for path in root.rglob('*') if recursive else root.iterdir():
        if cancelled():
            raise InterruptedError('Cancelled')
        if path.is_file() and path.suffix.lower() == '.zip':
            result.setdefault(path.name.lower(), str(path))
    return result
