# Laboratorium danych — desktop

Electron wraps the Streamlit app in a single window. The package contains CPython, installed dependencies and a snapshot of `app/` plus `exercises/dane/`. End users need neither Python nor a terminal. The launcher binds only to `127.0.0.1`, selects a free port and writes logs/cache under Electron's `userData` directory.

## Native build

Build each target on its own OS and architecture. Requirements: Node 24, npm, `curl`, `tar`, and network access for the initial dependency downloads. Linux additionally needs desktop libraries and `xvfb-run` for headless acceptance. Python is downloaded by the script; a system Python is unnecessary.

```bash
cd desktop
export npm_config_cache="$PWD/.cache/npm"
export ELECTRON_CACHE="$PWD/.cache/electron"
export ELECTRON_BUILDER_CACHE="$PWD/.cache/electron-builder"
npm ci
npm run prepare:python
npm run build -- --linux --x64
xvfb-run -a dist/linux-unpacked/laboratorium-danych --no-sandbox --smoke-test="$PWD/smoke_linux.png"
npm run validate:workflow
```

In PowerShell set the three build-only cache paths with `$env:npm_config_cache`, `$env:ELECTRON_CACHE` and `$env:ELECTRON_BUILDER_CACHE` instead of `export`. They are developer settings; users never set them. Build Windows with `npm run build -- --win --x64`. Build macOS with `npm run build -- --mac --arm64` or `--x64` on the matching host.

For macOS distribution, use the workflow's two-stage build: build `--dir`, run `codesign --force --deep --sign -` on the entire `.app`, verify it, then create the DMG with `electron-builder --prepackaged`. This retains the ad-hoc signature in the DMG. This is not Developer ID signing or notarization. Local direct DMG builds do not perform this explicit CI signing step.

The `--no-sandbox` flag is used only in the specified Linux headless acceptance command. Normal installed launches do not add it.

For development, run `npm run stage` after preparing Python, then `npm start`. A build always stages fresh sources. Staging excludes tests, caches, logs, virtual environments, `.env*` and key files. The app source and exercise directories are never edited. A SHA-256 file manifest in `staged/manifest.json` records the staged snapshot, including changes made by concurrent app development.

## Runtime and packaging

Exact versions: Electron 44.7.0, electron-builder 26.15.3, CPython 3.12.11, python-build-standalone release 20250818 (`install_only`). Runtime filenames and SHA-256 checksums are pinned in [python-lock.json](scripts/python-lock.json), from the [upstream release](https://github.com/astral-sh/python-build-standalone/releases/tag/20250818). The archive is verified before extraction on every preparation, including cached archives. Unsupported targets fail. Preparation recreates the runtime when requirements or its checksum change, runs pip dependency/import checks and installs exactly `app/requirements.txt`.

`package-lock.json` locks npm dependencies. Python direct requirements are pinned by the app; transitive Python dependencies follow pip resolution at build time. Full bit-for-bit reproducibility would require a per-platform Python dependency lock. Keep the runtime pin current after assessing upstream updates.

On npm 12, `allowScripts` explicitly permits the pinned Electron runtime download and electron-winstaller's architecture-selection script. Pip and builder temporary files stay in `.cache/pip/`. For this host's slow shared filesystem, the optional Linux acceptance helper mounts temporary RAM directories **inside a private user/mount namespace** at authorized project paths, runs the same build/tests, then copies the AppImage back to the on-disk `dist/` directory:

```bash
unshare --user --map-root-user --mount bash scripts/local-linux-acceptance.sh /absolute/task-directory
```

This helper needs Linux user namespaces, mount and Xvfb support. It also provides private shared memory and a short `/proc/<pid>/fd/<fd>` alias to the authorized temporary directory for Chrome's Unix socket. Its mounts disappear when the process ends. It does not change the host's mount namespace. It is a build-host workaround, not an end-user launch requirement.

`runtime/`, `staged/`, `dist/`, `node_modules/` and `.cache/` are ignored by Git. Cache paths stay inside `desktop/.cache`. Python wheels use `.cache/pip`. Packaging downloads use the two Electron cache variables. Remove these intermediates after acceptance if disk space is needed; retain the desired installer in `dist/`.

Internal child settings: `LAB_DESKTOP=1`, `LAB_USER_DIR=userData`, `DATA_DIR=resources/dane`, `LOG_DIR=userData/logs`, `CACHE_DIR=userData/cache`. The launcher also enables the existing app's Ollama discovery at `http://127.0.0.1:11434` and its custom endpoint UI. Settings persistence must be implemented by the app using `LAB_USER_DIR`; the launcher does not claim to persist session widgets or credentials.

The main window has context isolation, disabled Node integration and denied permission requests. HTTP(S)/mailto external links open in the system browser; downloads show a save dialog. The menu exposes reload, zoom, normal editing shortcuts, the user folder and quit. Closing the window stops Python on every OS. POSIX processes form their own group; Windows uses `taskkill /T /F`. An independent Python watchdog handles abrupt Electron death and uses a Windows Job Object with kill-on-close for descendant cleanup. Errors display a Polish dialog with `logs/serwer.log`; smoke mode reports failures without a blocking dialog. The current and previous server logs are retained.

The smoke flag creates an isolated `smoke-user-data/` profile beside the requested PNG, polls health for up to 90 seconds, then waits up to 90 seconds for the app title, at least five Streamlit tabs, an input and at least three download controls. Visible loading placeholders must disappear. Streamlit exceptions or error alerts fail the test. It captures the rendered window and exits 0; startup/render failures exit non-zero. The packaged runtime is used, not system Python. This verifies startup and rendering, not AI responses, all teaching workflows, clinical readiness or manuscript readiness.

## CI and artifacts

[desktop.yml](../.github/workflows/desktop.yml) runs manually and for tags `desktop-v*`. It builds Windows x64 (per-user NSIS and ZIP), macOS arm64 and x64 (DMG with ad-hoc signing), and Linux x64 (AppImage). Every job smoke-tests the unpacked packaged application and uploads its PNG/log evidence separately from installer artifacts. Linux uses Xvfb. Tag versions set the package version; all four successful jobs are required before a **draft** GitHub Release is created. Dispatch runs do not create releases. This worker does not push, tag or publish.

The [current GitHub runner list](https://github.com/actions/runner-images) lists `macos-14` as arm64; Intel macOS builds use `macos-15-intel` because GitHub [retired `macos-13`](https://github.com/actions/runner-images/issues/13046). The workflow fails explicitly if a runner's native architecture does not match its target. Workflow validation here uses YAML parsing and structural checks if actionlint is unavailable; it does not execute GitHub Actions. Windows/macOS build, installer behavior, Gatekeeper/SmartScreen prompts and live Ollama inference need validation on those systems.

The SVG is an icon placeholder. Confirm its native conversion on Windows/macOS and replace the placeholder before a branded release. Packages lack a publisher signature; macOS is not notarized. User-facing first-launch instructions are in [README_uzytkownik.md](README_uzytkownik.md).
