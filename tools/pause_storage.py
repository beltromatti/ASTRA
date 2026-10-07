#!/usr/bin/env python3
"""Preserve old worktree evidence, then remove reproducible development storage.

Private snapshots and compressed, content-addressed evidence stay in .pause/.
The installed game and its Application Support data are outside this tool's scope.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / '.pause'
STATE = STORE / 'state.json'
EPIC = Path('/Users/Shared/Epic Games/UE_5.8/Templates/TemplateResources/High/Characters/Content')
CHUNK = 2 ** 20
GENERATED = ('Binaries/', 'Intermediate/', 'DerivedDataCache/',
             'Saved/Cooked/', 'Saved/StagedBuilds/', 'Saved/Shaders/',
             'Saved/ShaderDebugInfo/', 'Saved/Temp/', 'mind/stt_server/bin/')
REMOVE = ('Binaries', 'Intermediate', 'DerivedDataCache',
          'Plugins/AstraMetalFX/Binaries', 'Plugins/AstraMetalFX/Intermediate',
          'Saved/Cooked', 'Saved/StagedBuilds', 'Saved/Shaders', 'Saved/ShaderDebugInfo', 'Saved/Temp',
          'mind/.venv', 'voice/.venv', 'mind/.ruff_cache',
          'Packaged/Mac', 'Packaged/Release/ASTRA.app')


def git(*args: str, cwd: Path = ROOT) -> str:
    return subprocess.check_output(['git', *args], cwd=cwd, text=True).strip()


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(CHUNK), b''):
            h.update(b)
    return h.hexdigest()


def write_state(state: dict) -> None:
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, indent=2) + '\n')
    tmp.chmod(0o600)
    tmp.replace(STATE)


def blob(path: Path) -> dict:
    st = path.lstat()
    if path.is_symlink():
        return {'link': os.readlink(path)}
    digest = sha(path)
    out = STORE / 'blobs' / (digest + '.gz')
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix('.tmp')
        with path.open('rb') as source, gzip.open(tmp, 'wb', compresslevel=3) as dest:
            shutil.copyfileobj(source, dest, CHUNK)
        h = hashlib.sha256()
        with gzip.open(tmp, 'rb') as source:
            for b in iter(lambda: source.read(CHUNK), b''):
                h.update(b)
        assert h.hexdigest() == digest, f'Archive verification failed: {path}'
        assert path.stat().st_mtime_ns == st.st_mtime_ns, f'File changed during archive: {path}'
        tmp.chmod(0o600)
        tmp.replace(out)
    return {'sha256': digest, 'size': st.st_size, 'mode': st.st_mode & 0o777, 'mtime_ns': st.st_mtime_ns}


def generated(worktree: Path, relative: str) -> bool:
    if relative.startswith(GENERATED) or relative.endswith(('.pyc', '.pyo', '.DS_Store')):
        return True
    if '/Binaries/' in relative or '/Intermediate/' in relative or '/__pycache__/' in relative:
        return True
    parts = Path(relative).parts
    for i, part in enumerate(parts):
        if part in ('.venv', 'venv') and (worktree.joinpath(*parts[:i + 1]) / 'pyvenv.cfg').is_file():
            return True
    if relative.startswith('Content/Characters/'):
        original = EPIC / relative.removeprefix('Content/Characters/')
        copy = worktree / relative
        return original.is_file() and copy.is_file() and sha(original) == sha(copy)
    return False


def worktrees() -> list[dict]:
    rows = []
    for block in git('worktree', 'list', '--porcelain').split('\n\n'):
        row = dict(line.split(' ', 1) for line in block.splitlines() if ' ' in line)
        if not row or Path(row['worktree']) == ROOT:
            continue
        path = Path(row['worktree'])
        assert path.resolve().is_relative_to(ROOT / '.claude/worktrees'), 'Unexpected worktree location'
        assert not path.is_symlink() and 'locked' not in block.splitlines(), 'Locked or linked worktree'
        row['name'] = path.name
        row['status'] = git('status', '--porcelain=v1', '--untracked-files=all', cwd=path)
        rows.append(row)
    return rows


def remove(path: Path, state: dict) -> None:
    if not path.exists():
        return
    assert not path.is_symlink(), f'Refusing linked directory: {path}'
    if path.is_relative_to(ROOT):
        relative = path.relative_to(ROOT).as_posix()
        assert not git('ls-files', '--', relative), f'Tracked files under {path}'
    else:
        site = ROOT.parent / 'astra-site'
        assert path.parent == site and path.name in ('node_modules', '.next', 'tsconfig.tsbuildinfo')
        assert not git('ls-files', '--', path.name, cwd=site)
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    state['removed'].append(str(path))
    write_state(state)


def freeze(releases_file: Path) -> None:
    if STATE.exists():
        previous = json.loads(STATE.read_text())
        assert not previous['complete'] and not previous['removed'] and not any(w.get('removed') for w in previous['worktrees']), 'A completed/partly removed snapshot already exists; inspect it first'
    assert not git('diff', '--name-only', '--', 'Content'), 'Content has local modifications'
    assert not git('diff', '--cached', '--name-only', '--', 'Content'), 'Content has staged modifications'
    commands = subprocess.check_output(['ps', '-axo', 'comm'], text=True).splitlines()
    assert not any('UnrealEditor' in c or (str(ROOT) in c and 'ASTRA-Mac' in c) for c in commands), 'Close the development editor/game first'
    STORE.mkdir(mode=0o700, exist_ok=True)
    state = {'version': 1, 'complete': False, 'root': str(ROOT),
             'free_before': shutil.disk_usage(ROOT).free, 'worktrees': [], 'removed': [], 'dehydrated': []}
    state['releases'] = json.loads(releases_file.read_text())
    samples = ROOT / 'art/_cache/vsco2'
    if samples.is_dir():
        assert not git('status', '--porcelain=v1', cwd=samples), 'Sample library has local changes'
        state['samples'] = {'revision': git('rev-parse', 'HEAD', cwd=samples),
                            'url': git('remote', 'get-url', 'origin', cwd=samples),
                            'sparse': git('sparse-checkout', 'list', cwd=samples).splitlines()}
    write_state(state)
    for row in worktrees():
        path = Path(row['worktree'])
        print(f"Preserving {row['name']}", flush=True)
        if row['status']:
            snapshot = git('stash', 'create', 'ASTRA development pause snapshot', cwd=path)
            if snapshot:
                ref = 'refs/astra/pause/' + row['name']
                git('update-ref', ref, snapshot)
                row['snapshot'] = ref
                # Make the tracked patch independently inspectable, in addition to the Git snapshot.
                patch = subprocess.check_output(['git', 'diff', '--binary', '--full-index', 'HEAD'], cwd=path)
                patch_path = STORE / (row['name'] + '.patch')
                patch_path.write_bytes(patch)
                patch_path.chmod(0o600)
        entries = []
        for flags in (['--others', '--ignored', '--exclude-standard'], ['--others', '--exclude-standard']):
            data = subprocess.check_output(['git', 'ls-files', '-z', *flags], cwd=path)
            for raw in data.split(b'\0'):
                if not raw:
                    continue
                relative = os.fsdecode(raw)
                if generated(path, relative):
                    continue
                file = path / relative
                if file.is_file() or file.is_symlink():
                    entries.append({'path': relative, **blob(file)})
                elif file.is_dir():
                    raise RuntimeError(f'Unclassified nested directory must be preserved separately: {file}')
        row['files'] = entries
        assert git('status', '--porcelain=v1', '--untracked-files=all', cwd=path) == row['status'], 'Worktree changed during preservation'
        state['worktrees'].append(row)
        write_state(state)
    # Every evidence blob has been verified before a single worktree is removed.
    for row in state['worktrees']:
        path = Path(row['worktree'])
        assert git('rev-parse', 'HEAD', cwd=path) == row['HEAD']
        assert git('status', '--porcelain=v1', '--untracked-files=all', cwd=path) == row['status']
        print(f"Removing preserved worktree {row['name']}", flush=True)
        subprocess.run(['git', 'worktree', 'remove', '--force', str(path)], cwd=ROOT, check=True)
        row['removed'] = True
        write_state(state)
    # Only replace tracked Content LFS payloads after verifying their exact local object.
    assets = json.loads(git('lfs', 'ls-files', '--json'))['files']
    for asset in assets:
        relative = asset['name']
        if not relative.startswith('Content/') or not asset['checkout']:
            continue
        path = ROOT / relative
        oid = asset['oid']
        obj = ROOT / '.git/lfs/objects' / oid[:2] / oid[2:4] / oid
        assert obj.is_file() and sha(obj) == oid and sha(path) == oid, f'LFS data not protected: {relative}'
        pointer = subprocess.check_output(['git', 'show', 'HEAD:' + relative], cwd=ROOT)
        assert pointer.startswith(b'version https://git-lfs.github.com/spec/v1\n')
        assert ('oid sha256:' + oid).encode() in pointer
        path.write_bytes(pointer)
        state['dehydrated'].append(relative)
    # Refresh pointer stat information without changing any indexed asset blob.
    git('add', '--', 'Content')
    assert not git('diff', '--cached', '--name-only', '--', 'Content'), 'An indexed Content blob changed'
    write_state(state)
    for relative in REMOVE:
        print('Removing generated ' + relative, flush=True)
        remove(ROOT / relative, state)
    # Published release ZIPs can be downloaded byte-for-byte; retain notes, checksum and Apple metadata.
    for release in state['releases']:
        for asset in release['assets']:
            zip_path = ROOT / 'Packaged/Release' / asset['name']
            if zip_path.is_file():
                assert asset.get('digest') and sha(zip_path) == asset['digest'].removeprefix('sha256:')
                remove(zip_path, state)
    if samples.is_dir():
        remove(samples, state)
    for path in ROOT.rglob('__pycache__'):
        if '.git' not in path.parts and '.pause' not in path.parts:
            remove(path, state)
    site = ROOT.parent / 'astra-site'
    for name in ('node_modules', '.next', 'tsconfig.tsbuildinfo'):
        remove(site / name, state)
    state['complete'] = True
    state['free_after'] = shutil.disk_usage(ROOT).free
    write_state(state)
    print(f"Pause complete; {len(state['worktrees'])} worktrees preserved", flush=True)


def restore_worktree(name: str) -> None:
    state = json.loads(STATE.read_text())
    row = next(w for w in state['worktrees'] if w['name'] == name)
    path = Path(row['worktree'])
    assert not path.exists(), 'Worktree already exists; refusing to overwrite it'
    subprocess.run(['git', 'worktree', 'add', str(path), row['branch'].removeprefix('refs/heads/')], cwd=ROOT, check=True)
    if row.get('snapshot'):
        subprocess.run(['git', 'stash', 'apply', '--index', row['snapshot']], cwd=path, check=True)
    if EPIC.is_dir():
        shutil.copytree(EPIC, path / 'Content/Characters', dirs_exist_ok=True)
    for file in row['files']:
        relative = Path(file['path'])
        assert not relative.is_absolute() and '..' not in relative.parts
        dest = path / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            original = EPIC / str(relative).removeprefix('Content/Characters/')
            assert str(relative).startswith('Content/Characters/') and original.is_file() and sha(dest) == sha(original), f'Existing file would be overwritten: {dest}'
        if 'link' in file:
            dest.symlink_to(file['link'])
            continue
        with gzip.open(STORE / 'blobs' / (file['sha256'] + '.gz'), 'rb') as source, dest.open('wb') as target:
            shutil.copyfileobj(source, target, CHUNK)
        assert sha(dest) == file['sha256'], 'Restored evidence failed verification'
        dest.chmod(file['mode'])
        os.utime(dest, ns=(file['mtime_ns'], file['mtime_ns']))
    print('Restored source snapshot and evidence:', path)


def restore_samples() -> None:
    state = json.loads(STATE.read_text())
    sample = state['samples']
    dest = ROOT / 'art/_cache/vsco2'
    if dest.exists():
        assert git('rev-parse', 'HEAD', cwd=dest) == sample['revision']
        print('Pinned sample library already present')
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(['git', 'clone', '--filter=blob:none', '--sparse', '--no-checkout', sample['url'], str(dest)], check=True)
    subprocess.run(['git', 'sparse-checkout', 'set', *sample['sparse']], cwd=dest, check=True)
    subprocess.run(['git', 'checkout', '--detach', sample['revision']], cwd=dest, check=True)


def verify() -> None:
    state = json.loads(STATE.read_text())
    seen = set()
    for row in state['worktrees']:
        assert git('rev-parse', row.get('snapshot', row['HEAD']))
        for file in row['files']:
            if 'sha256' not in file or file['sha256'] in seen:
                continue
            digest = file['sha256']
            h = hashlib.sha256()
            with gzip.open(STORE / 'blobs' / (digest + '.gz'), 'rb') as source:
                for b in iter(lambda: source.read(CHUNK), b''):
                    h.update(b)
            assert h.hexdigest() == digest
            seen.add(digest)
    print(f'Verified {len(seen)} unique preserved files and {len(state["worktrees"])} source references')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest='action', required=True)
    freeze_parser = sub.add_parser('freeze')
    freeze_parser.add_argument('--release-metadata', type=Path, required=True)
    wt = sub.add_parser('worktree')
    wt.add_argument('name')
    sub.add_parser('samples')
    sub.add_parser('verify')
    args = ap.parse_args()
    if args.action == 'freeze': freeze(args.release_metadata)
    elif args.action == 'worktree': restore_worktree(args.name)
    elif args.action == 'samples': restore_samples()
    else: verify()


if __name__ == '__main__':
    main()
