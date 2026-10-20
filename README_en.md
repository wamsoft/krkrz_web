<!-- source_hash: 3f62a8d5c3bd -->
# krkrz_web — Kirikiri Z for the browser

[日本語](README.md) | English

A wrapper repository for building Kirikiri Z (krkrz) with Emscripten (wasm32) and running it in the
browser. It uses SDL3 for the system layer, WebGL for drawing and pthreads (SharedArrayBuffer) for
threads.

- The engine and plugin sources come from [krkrz_dev](https://github.com/wamsoft/krkrz_dev) through
  `KRKRZ_BASE`. This repository holds only the browser-specific build definitions and the files used
  for serving (shell, startup script, tools)
- The wasm binary does not depend on any title: it is a **shared binary**. Engine resources
  (config.cf / messages / fonts and so on) are not built into the wasm but placed next to it as served
  files (sidecars). Switching titles only means replacing the sidecars, with no relinking
- The per-title settings (`web-config.json`) and assets can live in a separate folder (the project
  folder). Game data is delivered file by file on demand through `web://`
- `assetPack` (asset collection) shares its format with krkrz_android / krkrz_ios / krkrz_linux /
  krkrz_gdk. All plugins are linked statically, so there is no `cmake` section

## Requirements

- [emsdk](https://github.com/emscripten-core/emsdk) — `git clone https://github.com/emscripten-core/emsdk && ./emsdk install latest && ./emsdk activate latest`.
  Set the environment variable `EMSDK` to where it is installed (when not set, the default is
  `C:/work/emsdk`; `make EMSDK=<path>` also works)
- [vcpkg](https://github.com/microsoft/vcpkg) — set the environment variable `VCPKG_ROOT` to where it is installed
- [krkrz_dev](https://github.com/wamsoft/krkrz_dev) — clone it next to this repository (if you put it
  elsewhere, set the environment variable `KRKRZ_BASE` to its parent folder)
- CMake 3.22 or later / Ninja / Python 3 (used by the staging tools and the development server)
- A shell with GNU Make (Git Bash / MSYS2 and so on; needed to use the Makefile)

## Setup

1. Clone krkrz_dev and this repository into the same folder

   ```
   <KRKRZ_BASE>/
   ├── krkrz_dev/        ← git clone --recursive https://github.com/wamsoft/krkrz_dev.git
   └── krkrz_web/        ← this repository
   ```

2. Set the environment variables `EMSDK` and `VCPKG_ROOT` (`KRKRZ_BASE` defaults to the parent folder
   of this repository)

The engine at `${KRKRZ_BASE}/krkrz_dev/src/core` is pulled in with `add_subdirectory` (`CMakeLists.txt`).

## Building and running

```bash
export EMSDK=/path/to/emsdk      # the environment variable wins; default when not set: C:/work/emsdk

make prebuild    # cmake configure (runs vcpkg install)
make build       # build the shared binary
make run         # build + serve at http://localhost:8080/krkrz.html (the bundled sample; change with PORT=)
make serve       # start only the server

make PROJECT_DIR=/path/to/mygame run   # stage your own project folder and start it
```

The output is `krkrz.html` / `krkrz.js` / `krkrz.wasm` / `krkrz.data` under
`build/wasm32-emscripten/$BUILD_TYPE/krkrz/`, plus the sidecars (`resource/` / `resource.list` /
`webconfig.js`). Serve them with the COOP/COEP headers and they run as they are (see [Serving](#serving)).

| Task | Command |
|---|---|
| Build the shared binary | `make prebuild` → `make build` |
| Serve the sample | `make run` / `make serve` |
| Stage a project folder (only create the site) | `make PROJECT_DIR=/path/to/mygame web` |
| Build + stage + start | `make PROJECT_DIR=/path/to/mygame run` |
| Remove the build outputs | `make clean` |

Build options for the sample (data built in), startup arguments and URL parameters are in
[docs/web-build.md](docs/web-build.md) (in Japanese).

## Project folder (PROJECT_DIR)

This is the browser version of krkrz_android's `PROJECT_DIR` approach. Once you have built the shared
binary (`make prebuild build`; it does not depend on any title), just specifying a project folder writes
a **self-contained site under the project folder**. cmake is not called, so there is no relinking.

```bash
make PROJECT_DIR=/path/to/mygame web    # = python tools/stage_web.py /path/to/mygame
make PROJECT_DIR=/path/to/mygame run    # build → stage → start with the generated serve.py
#   → http://localhost:8100/   (port in web-config.json)
```

`${PROJECT_DIR}/build/web/site/` receives the shared binary (`krkrz.html` renamed to `index.html`),
the title's sidecars (`resource/` / `resource.list` / `webconfig.js`), `gamedata/` (the game data
delivered through web://) and `serve.py`. You can also run the generated `serve.py` directly.

- Files are hard-linked automatically (on the same drive nothing is duplicated; on another drive and
  similar cases it switches to copying file by file). From the second run on, files with the same size
  and modification time are skipped
- The generated site refers to no absolute paths, so it still works when you copy the whole folder or
  upload it to another host
- The title starts directly without any arguments in the URL

Details of the procedure are in [docs/web-config.md](docs/web-config.md) (in Japanese).

## web-config.json

`web-config.json` in the project folder specifies the display name, resources, startup arguments and
assets. Every key is optional; missing ones are filled in with conventional values (it is a separate
file from Android's `app-config.json`). Each key is described in
[docs/web-config.md](docs/web-config.md) (in Japanese).

| Key | Description |
|---|---|
| `name` | Display name (default: the folder name) |
| `resource` | Folder with config.cf / messages / fonts (default: `setup/nxresource`) |
| `port` | Default port of the generated `serve.py` (default: 8100) |
| `args` | Startup arguments that take precedence over config.cf (memory pool limits and so on) |
| `lowercase` | `true` lowercases (ASCII) the destination paths in `gamedata/` (for static hosting that is case-sensitive) |
| `assetPack` | Asset collection (format shared by the wrappers). The per-source `delivery` (`on-demand` / `prefetch`) is specific to the browser version |

For the format of `assetPack` and `${...}` path expansion, see
[Shared settings of the platform wrappers](https://wamsoft.github.io/krkrz_dev/en/topics/core/platform_config/)
on the documentation site.

> **Mind the 2GB limit of wasm32.** If the Bitmap / File / Krkrz / Sound memory pools add up to more
> than 2GB, startup fails with `Aborted(OOM)`. For titles whose config.cf sets large pools, shrink the
> pool sizes with `args` ([docs/web-config.md](docs/web-config.md#wasm32-の-2gb-上限とメモリプール)).

## Serving

Because pthreads (SharedArrayBuffer) are used, the server **must** return the following headers.

```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

`web/serve.py` and the `serve.py` generated by staging are development servers that serve with these
headers. itch.io can host it once "SharedArrayBuffer support" is turned on.

| Task | Details (in Japanese) |
|---|---|
| COOP/COEP, serving from case-sensitive servers, clearing the web:// cache (OPFS) | [docs/web-hosting.md](docs/web-hosting.md) |
| Where save data is stored and its identifiers (`-orgname` / `-appname`) — **always check before release** | [docs/web-save-data.md](docs/web-save-data.md) |
| The loading display during startup and "click to start" (audio gate) | [docs/web-loading.md](docs/web-loading.md) |
| Changing the look of the page (custom shell `web/shell.html`) | [docs/web-shell.md](docs/web-shell.md) |

## Feature support

| Feature | Status |
|---|---|
| Drawing (WebGL) | ○ OGLDrawDevice by default (SDLDrawDevice with `?drawdevice=sdl`). Linked with `-sFULL_ES3` |
| Threads (Timer / sound / image loading) | ○ pthreads + SharedArrayBuffer |
| TJS exceptions | ○ `-fwasm-exceptions` (required; without it a TJS error aborts immediately) |
| Static plugins | ○ csvParser / getSample / json / KAGParserEx / layerExBTOA / layerExImage / layerExRaster / layerExVector / saveStruct / scriptsEx / shrinkCopy / getLangName / textrender / tjsDataPack / tlgSliceLoader / psbfile / extrans / extNagano |
| Elements dialogs | ○ Besides the overlay kind, **modal ones (showModal\*) also work**. The default Asyncify works in every browser (`-DKRKRZ_WEB_ASYNC_BACKEND=JSPI` gives the JSPI version, limited to Chrome/Edge 137 or later) |
| Save data (`user://`) | ○ Persisted to IndexedDB automatically. Verified to survive reloads and restarts ([docs/web-save-data.md](docs/web-save-data.md)) |
| Movies (VideoOverlay) | ○ Played with the browser's `<video>` ([docs/web-video.md](docs/web-video.md)) |
| Console REPL / DAP | × (the devtools REPL takes its place) |

To add or remove plugins, edit `TVP_PLUGINS_STATIC` in `CMakeLists.txt` (wasm has no DLLs, so
everything is linked statically). When adding an old V2Link-style plugin, the hooks in Main.cpp must be
the `ONV2LINK()` / `ONV2UNLINK()` macro definitions (simplebinder.hpp). With a plain `onV2Link()`, the
symbols collide when several plugins are linked together.

## Development features

- **devtools console = TJS REPL** — evaluate any TJS expression from F12 → Console (not included in
  MASTER builds)

  ```js
  tjs('System.versionString')
  tjs('Debug.message("hello")')
  ```

- **Tools** — staging (`stage_web.py`), generating the web:// manifest (`gen_manifest.py`), a simple
  XP3 archiver (`xp3pack.py`) and laying out files for embedding on static hosts (`stage_docs.py`).
  [docs/web-tools.md](docs/web-tools.md)

## Documentation

The documents under `docs/` are in Japanese.

| Document | Contents |
|---|---|
| [docs/web-build.md](docs/web-build.md) | Resources as sidecars, building the sample (data built in), startup arguments and URL parameters |
| [docs/web-config.md](docs/web-config.md) | Staging a project folder, each key of `web-config.json`, memory pool limits |
| [docs/web-hosting.md](docs/web-hosting.md) | COOP/COEP, upper/lower case in file names, clearing the web:// cache (OPFS) |
| [docs/web-save-data.md](docs/web-save-data.md) | How save data is persisted, identifiers, behavior to know before release |
| [docs/web-loading.md](docs/web-loading.md) | The startup loading display (`loading.json`), the audio gate |
| [docs/web-shell.md](docs/web-shell.md) | How to modify the custom shell `web/shell.html` |
| [docs/web-video.md](docs/web-video.md) | How movie playback (VideoOverlay) is implemented, and caveats |
| [docs/web-tools.md](docs/web-tools.md) | The scripts in `tools/` |

The documentation for Kirikiri Z itself is on the [documentation site](https://wamsoft.github.io/krkrz_dev/en/).

## License

This repository (build scripts, the shell (HTML / JavaScript) and tools) is under the [MIT License](LICENSE).

The following, referenced or fetched at build time, follow their own licenses; the license of this
repository does not extend to them.

- The Kirikiri Z engine and plugins (each submodule under krkrz_dev)
- SDL3 (zlib License) and the dependency libraries fetched through vcpkg
- Emscripten

Include the license notices required in your distribution on the title side, according to the engine,
plugins and libraries you use.
