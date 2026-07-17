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

export EMSDK
export BUILD_TYPE

BUILD_DIR = build/$(PRESET)/$(BUILD_TYPE)

.PHONY: all prebuild build run serve clean

all: build

prebuild:
	cmake --preset $(PRESET) -DCMAKE_BUILD_TYPE=$(BUILD_TYPE) $(CMAKEOPT)

build:
	cmake --build $(BUILD_DIR)

run: build serve

serve:
	python web/serve.py $(BUILD_DIR)/krkrz $(PORT)

clean:
	cmake --build $(BUILD_DIR) --target clean
