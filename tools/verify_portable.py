"""Verify a portable release without starting Isaac, installing files, or opening a renderer."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def verify(archive, package_root=None):
    prefix = 'Soul-Fighter-Samira/'
    with zipfile.ZipFile(archive) as z:
        bad = z.testzip()
        if bad:
            raise ValueError(f'Corrupt ZIP member: {bad}')
        names = z.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate archive members')
        manifest = json.loads(z.read(prefix + 'SHA256SUMS.json'))
        expected = {prefix + n for n in manifest} | {prefix + 'SHA256SUMS.json'}
        actual = {n for n in names if not n.endswith('/')}
        if expected != actual:
            raise ValueError(f'Manifest coverage mismatch: {expected ^ actual}')
        for name, digest in manifest.items():
            if hashlib.sha256(z.read(prefix + name)).hexdigest() != digest:
                raise ValueError(f'SHA256 mismatch: {name}')
        roster = ET.fromstring(z.read(prefix + 'samira_testroom/content/players.xml'))
        assert {p.attrib['name'] for p in roster} == {'Samira', 'Yone', 'Miss Fortune'}
        metadata = ET.fromstring(z.read(prefix + 'samira_testroom/metadata.xml'))
        build = json.loads(z.read(prefix + 'BUILD.json'))
        assert metadata.findtext('version') == build['version'], 'Metadata and package versions differ'
        missing = []
        for name in names:
            if name.endswith('.anm2'):
                for sheet in ET.fromstring(z.read(name)).iter('Spritesheet'):
                    path = sheet.get('Path').replace('\\', '/')
                    candidates = [str(Path(name).parent / path).replace('\\', '/'),
                                  prefix + 'samira_testroom/resources/' + path,
                                  prefix + 'samira_testroom/resources/gfx/' + path]
                    if not any(c in actual for c in candidates):
                        missing.append((name, path))
        if missing:
            raise ValueError(f'Missing native sprite sheets: {missing}')
        for model in ('companion/src/samira/reference/source/model.glb',
                      'companion/assets/yone-local/yone.glb', 'companion/assets/mf-local/mf.glb'):
            assert z.read(prefix + model)[:4] == b'glTF', model
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.with_suffix('.zip.sha256').read_text().split()[0] == digest
    if package_root:
        companion = package_root / 'companion'
        # Embedded Python is isolated: explicitly provide packaged source paths.
        code = ("import sys,importlib;from pathlib import Path; r=Path(sys.argv[1]);"
                "sys.path[:0]=[str(r/'src/samira/external'),str(r/'tools')];"
                "mods='numpy PIL moderngl glfw model bridge layered_surface mf_renderer mf_taunt_doll mf_muzzle samira_audio yone_combat_audio run_testroom_renderer'.split();"
                "[importlib.import_module(m) for m in mods];print('Portable imports OK')")
        subprocess.run([str(companion / 'python/python.exe'), '-B', '-c', code, str(companion)], check=True)
        subprocess.run([str(companion / 'python/python.exe'), '-B', str(companion / 'tools/run_testroom_renderer.py'), '--help'], check=True)
    print(json.dumps({'archive': str(archive), 'sha256': digest, 'version': build['version'],
                      'verified_files': len(manifest), 'native_sprite_sheets': 'complete',
                      'portable_imports': bool(package_root)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--package-root', type=Path, help='Unpacked Soul-Fighter-Samira directory for portable import smoke checks.')
    args = parser.parse_args()
    verify(args.archive, args.package_root)
