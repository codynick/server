import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
paths = [root / 'install.sh', root / 'requirements.txt', root / '.dockerignore']
for folder in ('server', 'static', 'templates', 'runtime', 'deploy', 'upstream', 'tools'):
    paths.extend(p for p in (root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
manifest = {'version': '0.2.0', 'files': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}}
encoded = (json.dumps(manifest, indent=2) + '\n').encode()
(root / 'release.json').write_bytes(encoded)
setup = root / 'setup.sh'
lines = setup.read_text().splitlines()
lines = ['MANIFEST_SHA=' + hashlib.sha256(encoded).hexdigest() if line.startswith('MANIFEST_SHA=') else line for line in lines]
setup.write_text('\n'.join(lines) + '\n', newline='\n')
print('Sealed', len(paths), 'files')
