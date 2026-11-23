#!/usr/bin/env bash
# Builds the reply engine (llama.cpp + android/app/src/main/cpp/llm_engine.cpp + llm_c_api.cpp)
# for iPhone and the iOS Simulator, and packs it as ios/Frameworks/QuickTalkLLMC.xcframework,
# which Swift imports as `QuickTalkLLMC`. Run on a Mac with Xcode and CMake (brew install cmake).
# The first run clones llama.cpp (the pinned tag in CMakeLists.txt) into android/third_party/.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
cpp="$here/../android/app/src/main/cpp"
work="$here/.build/llm"
out="$here/Frameworks/QuickTalkLLMC.xcframework"
# iOS 17.2 needs an A12 or newer, all of which have the dot-product and half-float instructions.
arch="${QUICKTALK_ARM_ARCH:-armv8.2-a+dotprod+fp16}"

build() { # sdk
    local sdk="$1" dir="$work/$1"
    cmake -S "$cpp" -B "$dir" -G "Unix Makefiles" \
        -DCMAKE_SYSTEM_NAME=iOS \
        -DCMAKE_OSX_SYSROOT="$sdk" \
        -DCMAKE_OSX_ARCHITECTURES=arm64 \
        -DCMAKE_OSX_DEPLOYMENT_TARGET=17.2 \
        -DCMAKE_BUILD_TYPE=Release \
        -DGGML_NATIVE=OFF \
        -DGGML_CPU_ARM_ARCH="$arch" >/dev/null
    cmake --build "$dir" --target quicktalk_llm -j "$(sysctl -n hw.ncpu)"
    # One static library holding the engine, llama.cpp and ggml.
    libtool -static -o "$dir/libQuickTalkLLMC.a" $(find "$dir" -name '*.a' ! -name 'libQuickTalkLLMC.a')
}

headers="$work/include"
mkdir -p "$headers"
cp "$cpp/llm_c_api.h" "$headers/"
cat > "$headers/module.modulemap" <<'MAP'
module QuickTalkLLMC {
    header "llm_c_api.h"
    link "c++"
    link framework "Accelerate"
    export *
}
MAP

build iphoneos
build iphonesimulator

rm -rf "$out"
xcodebuild -create-xcframework \
    -library "$work/iphoneos/libQuickTalkLLMC.a" -headers "$headers" \
    -library "$work/iphonesimulator/libQuickTalkLLMC.a" -headers "$headers" \
    -output "$out"
echo "Built $out"
