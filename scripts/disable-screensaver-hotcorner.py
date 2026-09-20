#!/usr/bin/env python3
"""Remove only the Omarchy hot-corner command that force-launches the saver."""
import json
from datetime import datetime
from pathlib import Path
import shutil

path = Path.home() / '.config/omarchy/shell.json'
if not path.exists():
    raise SystemExit(0)
data = json.loads(path.read_text())
changed = 0

def visit(value):
    global changed
    if isinstance(value, dict):
        if value.get('id') == 'pi.hotcorners':
            for key in ('bottomLeftCommand', 'bottomRightCommand'):
                if value.get(key) == 'omarchy launch screensaver force':
                    value[key] = ''
                    changed += 1
        for child in value.values():
            visit(child)
    elif isinstance(value, list):
        for child in value:
            visit(child)

visit(data)
if changed:
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    shutil.copy2(path, path.with_name(path.name + '.bak-glide-hotcorner-' + stamp))
    path.write_text(json.dumps(data, indent=2) + '\n')
    print(f'Glide cleared {changed} screen-saver hot-corner command(s).')
