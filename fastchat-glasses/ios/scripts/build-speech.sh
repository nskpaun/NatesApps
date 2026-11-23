#!/usr/bin/env bash
# Build a static Swift-importable sherpa-onnx C API for iPhone and Apple Silicon Simulator.
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
work="$here/.build/speech"
source="$here/.build/sherpa-onnx"
ort_version=1.28.2
ort="$work/onnxruntime.xcframework"
out="$here/Frameworks/QuickTalkSpeechC.xcframework"

headers="$work/headers"
module="$headers/QuickTalkSpeechC"
mkdir -p "$module" "$here/Frameworks"
if [ ! -f "$source/CMakeLists.txt" ]; then
    git clone --depth 1 --branch v2.0.1 https://github.com/k2-fsa/sherpa-onnx.git "$source"
fi
if [ ! -f "$ort/Info.plist" ]; then
    curl -fL --retry 3 "https://github.com/csukuangfj/onnxruntime-libs/releases/download/v${ort_version}/onnxruntime-ios-static-xcframework-${ort_version}.xcframework.zip" -o "$work/ort.zip"
    unzip -oq "$work/ort.zip" -d "$work"
fi

cp "$source/sherpa-onnx/c-api/c-api.h" "$module/"
cat > "$module/module.modulemap" <<'MAP'
module QuickTalkSpeechC {
    header "c-api.h"
    link "c++"
    link framework "Accelerate"
    link framework "CoreML"
    link framework "Foundation"
    export *
}
MAP

build() {
    local platform="$1" slice="$2" dir="$work/$1"
    local framework="$ort/$slice/onnxruntime.framework"
    export SHERPA_ONNXRUNTIME_LIB_DIR="$ort/$slice"
    export SHERPA_ONNXRUNTIME_INCLUDE_DIR="$framework/Headers"
    cmake -S "$source" -B "$dir" \
        -DCMAKE_TOOLCHAIN_FILE="$source/toolchains/ios.toolchain.cmake" \
        -DPLATFORM="$platform" -DDEPLOYMENT_TARGET=17.2 \
        -DENABLE_BITCODE=0 -DENABLE_ARC=1 -DENABLE_VISIBILITY=0 \
        -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
        -DSHERPA_ONNX_ENABLE_PYTHON=OFF -DSHERPA_ONNX_ENABLE_BINARY=OFF \
        -DSHERPA_ONNX_ENABLE_TESTS=OFF -DSHERPA_ONNX_ENABLE_CHECK=OFF \
        -DSHERPA_ONNX_ENABLE_PORTAUDIO=OFF -DSHERPA_ONNX_ENABLE_JNI=OFF \
        -DSHERPA_ONNX_ENABLE_C_API=ON -DSHERPA_ONNX_ENABLE_WEBSOCKET=OFF
    cmake --build "$dir" --target sherpa-onnx-c-api -j "${QUICKTALK_BUILD_JOBS:-6}"
    # The upstream iOS build uses the same archives. Include ONNX Runtime so the
    # app only has one static speech dependency to link.
    local archives=()
    local name
    for name in kaldi-native-fbank-core kissfft-float sherpa-onnx-c-api sherpa-onnx-core \
        sherpa-onnx-fstfar ssentencepiece_core utf8proc sherpa-onnx-fst sherpa-onnx-kaldifst-core kaldi-decoder-core; do
        archives+=("$dir/lib/lib$name.a")
    done
    local runtime="$framework/onnxruntime"
    if [ "$platform" = SIMULATORARM64 ]; then
        xcrun lipo "$runtime" -thin arm64 -output "$dir/libonnxruntime-arm64.a"
        runtime="$dir/libonnxruntime-arm64.a"
    fi
    xcrun libtool -static -o "$dir/libQuickTalkSpeechC.a" "${archives[@]}" "$runtime"
}

build OS64 ios-arm64
build SIMULATORARM64 ios-arm64_x86_64-simulator
rm -rf "$out"
xcodebuild -create-xcframework \
    -library "$work/OS64/libQuickTalkSpeechC.a" -headers "$headers" \
    -library "$work/SIMULATORARM64/libQuickTalkSpeechC.a" -headers "$headers" \
    -output "$out"
