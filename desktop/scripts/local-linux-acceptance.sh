#!/usr/bin/env bash
# Optional local workaround for slow shared storage. Run using:
# unshare --user --map-root-user --mount bash scripts/local-linux-acceptance.sh /absolute/evidence-directory
# Mounts exist only in this private namespace; final AppImage is copied to on-disk dist/.
set -euo pipefail
cd "$(dirname "$0")/.."
evidence_dir=$(realpath "$1")
mkdir -p "$evidence_dir" .cache/fast .cache/output .cache/pip node_modules runtime staged dist
mount --make-rprivate /
mount --bind "$PWD/dist" "$PWD/.cache/output"
mount -t tmpfs -o size=6G tmpfs "$PWD/.cache/fast"
for build_dir in node_modules runtime staged dist; do
  mkdir -p ".cache/fast/$build_dir"
  mount --bind "$PWD/.cache/fast/$build_dir" "$PWD/$build_dir"
done
mkdir -p .cache/fast/pip
mount --bind "$PWD/.cache/fast/pip" "$PWD/.cache/pip"
mkdir -p .cache/fast/shm
chmod 1777 .cache/fast/shm
mount --bind "$PWD/.cache/fast/shm" /dev/shm
mkdir -p .cache/fast/tmp
# Chrome's SingletonSocket path must fit Linux's 108-byte Unix socket limit.
# Keep storage in the authorized RAM directory, with a short live descriptor alias.
exec {socket_tmp_fd}< "$PWD/.cache/fast/tmp"
export TMPDIR="/proc/$$/fd/$socket_tmp_fd"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export npm_config_cache="$PWD/.cache/fast/npm"
export ELECTRON_CACHE="$PWD/.cache/fast/electron"
export ELECTRON_BUILDER_CACHE="$PWD/.cache/fast/electron-builder"
export CSC_IDENTITY_AUTO_DISCOVERY=false
if test -n "${HTTPS_PROXY:-}"; then
  export ELECTRON_GET_USE_PROXY=1
  export GLOBAL_AGENT_HTTPS_PROXY="$HTTPS_PROXY"
  export GLOBAL_AGENT_HTTP_PROXY="${HTTP_PROXY:-$HTTPS_PROXY}"
fi
if test -f package-lock.json; then
  npm ci > "$evidence_dir/npm_install.log" 2>&1
else
  npm install > "$evidence_dir/npm_install.log" 2>&1
fi
npm run validate:workflow > "$evidence_dir/workflow_validation.log" 2>&1
npm run prepare:python > "$evidence_dir/prepare_python.log" 2>&1
npm run build -- --linux --x64 > "$evidence_dir/build_linux.log" 2>&1
xvfb-run -a -f "$PWD/.cache/fast/Xauthority-smoke" dist/linux-unpacked/laboratorium-danych --no-sandbox --smoke-test="$evidence_dir/smoke_linux.png" > "$evidence_dir/smoke_linux.log" 2>&1
xvfb-run -a -f "$PWD/.cache/fast/Xauthority-lifecycle" node scripts/check-linux-lifecycle.mjs "$evidence_dir" > "$evidence_dir/lifecycle_linux.log" 2>&1
cp staged/manifest.json "$evidence_dir/staged_manifest.json"
runtime/linux-x64/python/bin/python3 -m pip freeze > "$evidence_dir/python_packages_linux.txt"
cp dist/*.AppImage .cache/output/
sha256sum .cache/output/*.AppImage > "$evidence_dir/artifact_sha256.txt"
stat --format='%n: %s bytes' .cache/output/*.AppImage > "$evidence_dir/artifact_size.txt"
cat "$evidence_dir/workflow_validation.log" "$evidence_dir/smoke_linux.log" "$evidence_dir/lifecycle_linux.log" "$evidence_dir/artifact_size.txt"
printf 'Local Linux acceptance completed; exit code 0.\n'
