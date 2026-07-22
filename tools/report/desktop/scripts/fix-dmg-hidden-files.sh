#!/usr/bin/env bash
# Copyright (c) 2026 Martin.Bechard@DevConsult.ca
# AI attribution: Generated with AI assistance.
# Responsibility: Remove installer-only icon artifacts from packaged Agent Report disk images.

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "Skipping DMG hidden-file normalization outside macOS."
  exit 0
fi

input_path="${1:-../target/release/bundle/dmg}"

cleanup_device=""
cleanup_directory=""

cleanup() {
  if [[ -n "$cleanup_device" ]]; then
    hdiutil detach "$cleanup_device" >/dev/null 2>&1 || true
  fi
  if [[ -n "$cleanup_directory" && -d "$cleanup_directory" ]]; then
    rm -rf "$cleanup_directory"
  fi
}

trap cleanup EXIT

attach_image() {
  local image_path="$1"
  local mount_path="$2"
  local access_mode="$3"

  hdiutil attach \
    "$access_mode" \
    -noverify \
    -noautoopen \
    -nobrowse \
    -mountpoint "$mount_path" \
    "$image_path" \
    | awk '/^\/dev\// { print $1; exit }'
}

fix_dmg() {
  local dmg_path="$1"
  local dmg_name
  local work_directory
  local read_write_image
  local compressed_image
  local mount_directory
  local verify_directory
  local root_attributes

  dmg_name="$(basename "$dmg_path")"
  work_directory="$(mktemp -d "${TMPDIR:-/tmp}/agent-report-dmg.XXXXXX")"
  cleanup_directory="$work_directory"
  read_write_image="$work_directory/read-write.dmg"
  compressed_image="$work_directory/compressed.dmg"
  mount_directory="$work_directory/mount"
  verify_directory="$work_directory/verify"
  mkdir -p "$mount_directory" "$verify_directory"

  echo "Removing installer icon artifacts from $dmg_name..."
  hdiutil convert "$dmg_path" -format UDRW -o "$read_write_image" >/dev/null

  cleanup_device="$(attach_image "$read_write_image" "$mount_directory" -readwrite)"
  if [[ -e "$mount_directory/.VolumeIcon.icns" ]]; then
    rm -f -- "$mount_directory/.VolumeIcon.icns"
  fi
  if [[ -x /usr/bin/SetFile ]]; then
    /usr/bin/SetFile -a c "$mount_directory"
  else
    xattr -d com.apple.FinderInfo "$mount_directory" >/dev/null 2>&1 || true
  fi
  sync
  hdiutil detach "$cleanup_device" >/dev/null
  cleanup_device=""

  hdiutil convert \
    "$read_write_image" \
    -format UDZO \
    -imagekey zlib-level=9 \
    -o "$compressed_image" \
    >/dev/null
  mv "$compressed_image" "$dmg_path"

  cleanup_device="$(attach_image "$dmg_path" "$verify_directory" -readonly)"
  if [[ -e "$verify_directory/.VolumeIcon.icns" ]]; then
    echo ".VolumeIcon.icns is still present in $dmg_name." >&2
    exit 1
  fi
  if [[ -x /usr/bin/GetFileInfo ]]; then
    root_attributes="$(/usr/bin/GetFileInfo -a "$verify_directory")"
    if [[ "$root_attributes" == *C* ]]; then
      echo "The custom volume icon flag is still set in $dmg_name ($root_attributes)." >&2
      exit 1
    fi
  fi
  hdiutil detach "$cleanup_device" >/dev/null
  cleanup_device=""

  rm -rf "$work_directory"
  cleanup_directory=""
  echo "Verified installer icon artifacts are absent from $dmg_name."
}

found_dmg=0
if [[ -f "$input_path" ]]; then
  fix_dmg "$input_path"
  found_dmg=1
elif [[ -d "$input_path" ]]; then
  while IFS= read -r -d '' dmg_path; do
    fix_dmg "$dmg_path"
    found_dmg=1
  done < <(find "$input_path" -maxdepth 1 -type f -name '*.dmg' -print0)
else
  echo "DMG path does not exist: $input_path" >&2
  exit 1
fi

if [[ "$found_dmg" -eq 0 ]]; then
  echo "No DMG files were found at: $input_path" >&2
  exit 1
fi
