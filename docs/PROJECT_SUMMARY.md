# Project summary

Orientation for someone opening this repo for the first time.

## What it is

**ac-telemetry** is a headless Raspberry Pi service that will log Assetto Corsa (PS5) telemetry from an HDMI capture path. Today (Slice 0) it only proves capture and service shape: open a mock or V4L2 source, expose health/metrics/UI, write a CSV session stub.

## What it is not

- Not [acc-telemetry](https://github.com/blofelds/acc-telemetry) (offline video-file extractor)
- Not a lap timer yet
- Not a cloud service

## Who it is for

Gary Blofeld — home sim setup: PS5 → splitter → USB capture → Pi, phone on LAN for status (later: session metadata and live laps).

## Stack in one line

Python · FastAPI · Prometheus client · optional OpenCV · CSV files · systemd on Raspberry Pi OS.

## Mental model

Think “small appliance,” not “platform.” One process, one bind address, one CSV folder. Features arrive as slices; each slice should stay reviewable as one focused PR.

## Where to read next

1. Root [README.md](../README.md)
2. [USER_GUIDE.md](USER_GUIDE.md)
3. [ARCHITECTURE.md](ARCHITECTURE.md)
4. [FEATURES.md](FEATURES.md)
