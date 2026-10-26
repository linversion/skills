#!/bin/bash
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "$0")" && pwd -P)
app="$script_dir/../assets/When will Tibo reset.app"
build_dir=$(mktemp -d "${TMPDIR:-/tmp/}tibo-notifier.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
sdk=$(xcrun --sdk macosx --show-sdk-path)

for arch in arm64 x86_64; do
    xcrun swiftc -swift-version 5 -O -sdk "$sdk" \
        -target "${arch}-apple-macosx11.0" \
        "$script_dir/NativeNotifier.swift" \
        -o "$build_dir/notifier-$arch"
done
xcrun lipo -create "$build_dir/notifier-arm64" "$build_dir/notifier-x86_64" \
    -output "$build_dir/AIHotNotifier"
install -m 755 "$build_dir/AIHotNotifier" "$app/Contents/MacOS/AIHotNotifier"
codesign --force --sign - --identifier com.aihot.codex-reset-monitor.notifier "$app"
codesign --verify --strict "$app"
file "$app/Contents/MacOS/AIHotNotifier"
