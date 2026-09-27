# Project summary

Orientation for someone opening this repo for the first time.

## What it is

**ac-telemetry** is a headless Raspberry Pi service that logs Assetto Corsa (PS5) telemetry from an HDMI capture path. Today it proves capture, lets you create/end driving sessions from a phone (track, car, notes), and records **lap times** to CSV (mock reader by default; optional tesseract), with Prometheus metrics.

## What it is not

- Not [acc-telemetry](https://github.com/blofelds/acc-telemetry) (offline video-file extractor)
- Not a sector / throttle / brake logger yet
- Not a cloud service

## Who it is for

Gary Blofeld — home sim setup: PS5 → splitter → USB capture → Pi, phone on LAN for sessions and live lap times.

## Stack in one line

Python · FastAPI · Prometheus client · optional OpenCV · CSV files · systemd on Raspberry Pi OS.

## Mental model

Think “small appliance,” not “platform.” One process, one bind address, one CSV folder, one open session. Capture owns frames; detect samples a tiny ROI at low FPS and must never block the capture thread.

## Where to read next

1. Root [README.md](../README.md)
2. [USER_GUIDE.md](USER_GUIDE.md)
3. [ARCHITECTURE.md](ARCHITECTURE.md)
4. [FEATURES.md](FEATURES.md)
