# Deploy on Raspberry Pi (systemd)

Runs **ac-telemetry** as a **system** unit under non-root `User=pi` (not root).
Survives logout and starts on boot after `enable`.

## Layout (default unit paths)

| Path | Role |
| --- | --- |
| `/opt/ac-telemetry` | Clone + working directory (owned by `pi`) |
| `/opt/ac-telemetry/.venv` | Venv with `ac-telemetry` on `PATH` (`ExecStart`) |
| `/etc/systemd/system/ac-telemetry.service` | Installed unit |

CSV / recordings land under `/opt/ac-telemetry/data/` because `WorkingDirectory` is the install tree.

### If the tree is not under `/opt`

Edit these keys in the unit (or a drop-in) before enable:

- `WorkingDirectory=`
- `ExecStart=`
- `ReadWritePaths=`
- set `ProtectHome=read-only` or `false` if the tree is under `/home/…` (default `ProtectHome=true` blocks home)

Keep `User=pi` / `Group=pi` / `SupplementaryGroups=video`.

## One-time install

```bash
# 1) Tree + venv (Pi 2B: apt OpenCV + system-site-packages)
sudo mkdir -p /opt/ac-telemetry
sudo chown pi:pi /opt/ac-telemetry
git clone https://github.com/blofelds/ac-telemetry.git /opt/ac-telemetry
cd /opt/ac-telemetry
sudo apt update
sudo apt install -y python3-opencv python3-venv v4l-utils
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e .

# 2) video group (re-login / reboot if newly added)
sudo usermod -aG video pi
groups   # must list video

# 3) Install unit + enable at boot
sudo ./deploy/install-systemd.sh
# equivalent:
#   sudo install -m 644 deploy/ac-telemetry.service /etc/systemd/system/
#   sudo systemctl daemon-reload
#   sudo systemctl enable --now ac-telemetry.service
```

## Day-to-day

```bash
sudo systemctl status ac-telemetry
sudo journalctl -u ac-telemetry -f
sudo systemctl restart ac-telemetry
```

UI: `http://<pi-ip>:8741/`

## Hardening notes

The unit sets `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome=true`,
`DevicePolicy=closed` + `DeviceAllow=char-video`, and `ReadWritePaths=/opt/ac-telemetry`.
Runtime is still `pi` + `video` — never root.
