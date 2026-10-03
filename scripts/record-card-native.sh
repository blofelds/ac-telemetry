#!/usr/bin/env bash
# Record a card-native 1280x720 clip from /dev/video0 with ffmpeg.
#
# HITL GATE: Only run this when the ac-telemetry runtime capture is STOPPED.
# Opening /dev/video0 while the service holds it will fail or fight the device.
# Prefer in-app tee while runtime is live:
#   curl -sS -X POST http://127.0.0.1:8741/api/debug/record/start \
#     -H 'Content-Type: application/json' -d '{"duration_seconds":60}'
#
# Usage:
#   scripts/record-card-native.sh [seconds] [output_dir]
# Defaults: 30 seconds, ~/ac-telemetry-testdata/card

set -euo pipefail

SECONDS_DUR="${1:-30}"
OUT_DIR="${2:-${HOME}/ac-telemetry-testdata/card}"
DEVICE="${AC_TELEMETRY_DEVICE:-/dev/video0}"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="${OUT_DIR}/${STAMP}_card_1280x720.mkv"

mkdir -p "${OUT_DIR}"

if [[ ! -e "${DEVICE}" ]]; then
  echo "error: capture device not found: ${DEVICE}" >&2
  exit 1
fi

# Best-effort busy check: if something already has the device, warn loudly.
if command -v fuser >/dev/null 2>&1; then
  if fuser "${DEVICE}" >/dev/null 2>&1; then
    echo "error: ${DEVICE} is busy (is ac-telemetry still capturing?)." >&2
    echo "Stop the runtime first, or use POST /api/debug/record/start instead." >&2
    exit 1
  fi
fi

echo "Recording ${SECONDS_DUR}s from ${DEVICE} → ${OUT}"
echo "(no scale/crop — card-native 1280x720)"

# Prefer MJPEG copy when the UVC path is MJPEG (matches runtime prefer_mjpeg).
if ffmpeg -hide_banner -f v4l2 -framerate 30 -video_size 1280x720 -input_format mjpeg \
  -i "${DEVICE}" -t "${SECONDS_DUR}" -c:v copy "${OUT}"; then
  echo "Wrote ${OUT}"
  exit 0
fi

echo "MJPEG copy failed; retrying with libx264 re-encode (still 1280x720, no scale)…" >&2
OUT_MP4="${OUT_DIR}/${STAMP}_card_1280x720.mp4"
ffmpeg -hide_banner -f v4l2 -framerate 30 -video_size 1280x720 \
  -i "${DEVICE}" -t "${SECONDS_DUR}" \
  -c:v libx264 -crf 18 -pix_fmt yuv420p "${OUT_MP4}"
echo "Wrote ${OUT_MP4}"
