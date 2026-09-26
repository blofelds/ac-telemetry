# Project summary

Orientation for someone opening this repo for the first time.

## What it is

**ac-telemetry** is a headless Raspberry Pi service that will log Assetto Corsa (PS5) telemetry from an HDMI capture path. Today (Slice 1) it proves capture **and** lets you create/end driving sessions from a phone (track, car, notes) persisted as CSV, with Prometheus session counters.

## What it is not

- Not [acc-telemetry](https://github.com/blofelds/acc-telemetry) (offline video-file extractor)
- Not a lap timer yet (Slice 2)
- Not a cloud service

## Who it is for

Gary Blofeld — home sim setup: PS5 → splitter → USB capture → Pi, phone on LAN for session metadata (later: live laps).

## Stack in one line

Python · FastAPI · Prometheus client · optional OpenCV · CSV files · systemd on Raspberry Pi OS.

## Mental model

Think “small appliance,” not “platform.” One process, one bind address, one CSV folder, one open session. Features arrive as slices; each slice should stay reviewable as one focused PR.

## Where to read next

1. Root [README.md](../README.md)
2. [USER_GUIDE.md](USER_GUIDE.md)
3. [ARCHITECTURE.md](ARCHITECTURE.md)
4. [FEATURES.md](FEATURES.md)
