#!/usr/bin/env bash
set -euo pipefail
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
target="$HOME/.config/omarchy/plugins/nixfred.glide"
if [[ -L "$target" ]]; then
  unlink "$target"
fi
mkdir -p "$target/scripts"
cp "$source_dir/Layout.qml" "$target/Layout.qml"
cp "$source_dir"/scripts/*.py "$target/scripts/"
cp "$source_dir/remote-install.sh" "$target/remote-install.sh"
cp "$source_dir/manifest.json" "$target/manifest.json"
omarchy plugin validate "$target"
omarchy-shell shell rescanPlugins
