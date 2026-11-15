#!/usr/bin/env bash
# Install the system unit and enable it at boot (needs root once).
# Expects the recommended layout: /opt/ac-telemetry with .venv ready.
# Edit deploy/ac-telemetry.service first if WorkingDirectory / ExecStart differ.
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "run as root: sudo $0" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="${ROOT}/deploy/ac-telemetry.service"
UNIT_DST=/etc/systemd/system/ac-telemetry.service

if [[ ! -f "${UNIT_SRC}" ]]; then
  echo "missing unit: ${UNIT_SRC}" >&2
  exit 1
fi

install -m 644 "${UNIT_SRC}" "${UNIT_DST}"
systemctl daemon-reload
systemctl enable --now ac-telemetry.service
systemctl --no-pager --full status ac-telemetry.service
