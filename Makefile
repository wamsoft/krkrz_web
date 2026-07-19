# krkrz_web build wrapper (Git Bash / MSYS2 の make を想定)
#
#   make prebuild   # cmake configure (vcpkg install が走る)
#   make build      # cmake --build
#   make run        # build + COOP/COEP 付きローカルサーバで配信
#   make serve      # サーバのみ起動
#   make clean
#
# 必要な環境変数:
#   VCPKG_ROOT  vcpkg のルート
#   EMSDK       emsdk のルート (既定: D:/work/emsdk)
#   KRKRZ_BASE  krkrz_dev の親フォルダ (既定: このリポジトリの親)

PRESET ?= wasm32-emscripten
BUILD_TYPE ?= Release
EMSDK ?= D:/work/emsdk
PORT ?= 8080
CMAKEOPT ?=

# 案件フォルダ (任意で web-config.json を持つ)。`make PROJECT_DIR=<path> web` で
# 共有バイナリ (make build 済) をコピーし、案件の resource/webconfig/gamedata を
# サイドカー配置して ${PROJECT_DIR}/build/web/site へ出力する (cmake は呼ばない)。
# `make PROJECT_DIR=<path> run` は build → ステージング → 生成 serve.py で起動まで一括。
# gamedata の配置はハードリンク自動判定 (別ボリュームは copy に自動フォールバック)。
PROJECT_DIR ?=

export EMSDK
export BUILD_TYPE

BUILD_DIR = build/$(PRESET)/$(BUILD_TYPE)

.PHONY: all prebuild build run serve clean web

all: build

# 案件フォルダ (PROJECT_DIR) を web サイトとしてステージング (共有バイナリは make build 済前提)。
# gamedata はハードリンク自動判定で配置 (同一ドライブ=実体複製なし / 別ドライブ=copy 自動)。
# 例: make PROJECT_DIR=/path/to/game web
web:
	@test -n "$(PROJECT_DIR)" || (echo "PROJECT_DIR を指定してください (make PROJECT_DIR=<path> web)"; exit 2)
	python tools/stage_web.py "$(PROJECT_DIR)" --build-type $(BUILD_TYPE)

prebuild:
	cmake --preset $(PRESET) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) $(CMAKEOPT)

build:
	cmake --build $(BUILD_DIR)

# run:
#   PROJECT_DIR 指定あり … 共有バイナリを build → 案件を site にステージング →
#                          生成された serve.py で起動 (引数なし URL で案件が立ち上がる)
#   指定なし           … サンプルランチャを build → web/serve.py で配信
run:
	@if [ -n "$(PROJECT_DIR)" ]; then \
	  $(MAKE) build && \
	  python tools/stage_web.py "$(PROJECT_DIR)" --build-type $(BUILD_TYPE) && \
	  python "$(PROJECT_DIR)/build/web/site/serve.py" ; \
	else \
	  $(MAKE) build && python web/serve.py $(BUILD_DIR)/krkrz $(PORT) ; \
	fi

serve:
	python web/serve.py $(BUILD_DIR)/krkrz $(PORT)

clean:
	cmake --build $(BUILD_DIR) --target clean
