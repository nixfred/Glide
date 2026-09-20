#!/usr/bin/env python3
import hashlib, json, os, shutil, subprocess, sys, tarfile
from pathlib import Path
archive=Path(sys.argv[1])
home=Path.home()
backup=home/'.local/state/omarchy/glide/handoff-20260919'
backup.mkdir(parents=True,exist_ok=True)
protected=[home/'.config/hypr'/n for n in ['hyprland.lua','bindings.lua','input.lua','clipboard.lua','copilot.lua']]
before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in protected if p.exists()}
(backup/'input-config-before.json').write_text(json.dumps(before,indent=2))
with tarfile.open(archive) as t:
    t.extractall(backup/'payload', filter='data')
payload=backup/'payload'
files={
    'omarchy-glide-engine':home/'.local/bin/omarchy-glide-engine',
    'mouse-owner.py':home/'.config/omarchy/plugins/nixfred.glide/scripts/mouse-owner.py',
    'Layout.qml':home/'.config/omarchy/plugins/nixfred.glide/Layout.qml',
    'manifest.json':home/'.config/omarchy/plugins/nixfred.glide/manifest.json',
    'omarchy-glide-owner.service':home/'.config/systemd/user/omarchy-glide-owner.service',
    'omarchy-glide.service':home/'.config/systemd/user/omarchy-glide.service',
}
for name,target in files.items():
    saved=backup/('before-'+name)
    if target.exists() and not saved.exists(): shutil.copy2(target,saved)
    stage=target.with_name(target.name+'.new')
    shutil.copy2(payload/name,stage)
    if name=='omarchy-glide-engine': stage.chmod(0o755)
    os.replace(stage,target)
subprocess.run(['systemctl','--user','daemon-reload'],check=True)
subprocess.run(['systemctl','--user','restart','omarchy-glide.service'],check=True)
subprocess.run(['systemctl','--user','restart','omarchy-glide-owner.service'],check=True)
subprocess.run(['systemctl','--user','is-active','omarchy-glide.service','omarchy-glide-owner.service'],check=True)
after={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in before}
assert before==after, 'Input configuration unexpectedly changed'
(backup/'deployment.json').write_text(json.dumps({'protected_unchanged':True,'engine_sha256':hashlib.sha256(files['omarchy-glide-engine'].read_bytes()).hexdigest()},indent=2))
print('Protected keyboard configurations unchanged; backup: '+str(backup))
