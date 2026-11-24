"""Record non-secret source identity and a static module inventory; no .env reads."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[2]
def git(*args):
    return subprocess.check_output(['git', *args], cwd=root, text=True, encoding='utf-8')

paths = sorted(set(git('ls-files', '--cached', '--others', '--exclude-standard').splitlines()))
allowed = {'.py', '.ts', '.tsx', '.js', '.cjs', '.mjs', '.json', '.sql', '.md', '.yml', '.yaml', '.toml', '.txt', '.j2', '.lock', '.html', '.css'}
manifest, inventory = [], []
for name in paths:
    path = root / name
    if name.startswith('docs/benchmarks/') or '.env' in path.name or path.suffix not in allowed or not path.is_file():
        continue
    content = path.read_bytes()
    manifest.append(dict(path=name, bytes=len(content), sha256=hashlib.sha256(content).hexdigest()))
    if name.startswith(('backend/app/', 'backend/scripts/', 'backend/tests/', 'frontend/src/', 'frontend/tests/', 'frontend/e2e/', 'extension/')):
        row = dict(path=name, lines=len(content.splitlines()))
        if path.suffix == '.py':
            tree = ast.parse(content.decode('utf-8-sig'))
            row['definitions'] = [dict(name=n.name, line=n.lineno, kind=type(n).__name__) for n in ast.walk(tree)
                                  if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))]
        inventory.append(row)
raw = root / 'docs/benchmarks/raw'
(raw / 'source-manifest.json').write_text(json.dumps(dict(head=git('rev-parse', 'HEAD').strip(),
    snapshot='working tree, including uncommitted and untracked source; excludes secrets, generated benchmark outputs, binary data and ignored files', files=manifest), indent=2), encoding='utf-8')
(raw / 'source-inventory.json').write_text(json.dumps(inventory, indent=2), encoding='utf-8')
(raw / 'git-status.txt').write_text(git('status', '--short'), encoding='utf-8')
print(json.dumps({'manifest_files': len(manifest), 'inventoried_modules': len(inventory)}))
