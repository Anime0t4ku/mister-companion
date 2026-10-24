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
            parts = value.removeprefix('/').split('/')
            if (value.startswith('//') or any(
                    not re.fullmatch(r'[\w .()+\-]+', part, re.ASCII)
                    or part in {'.', '..'} for part in parts)):
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
            relative = path.relative_to(root).as_posix().lower()
            result.setdefault(relative, str(path))
            result.setdefault('/' + relative, str(path))
            result.setdefault('/' + root.name.lower() + '/' + relative, str(path))
    return result


def destination_zip_path(folder, name):
    """MRA leading slashes refer to the games root, above games/mame."""
    import posixpath
    base = folder.replace('\\', '/')
    return posixpath.join(posixpath.dirname(base.rstrip('/')) if name.startswith('/') else base,
                          name.lstrip('/'))
