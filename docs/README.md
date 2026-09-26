# AC Telemetry — Documentation Index

Documentation follows the same **layout philosophy** as [blofelds/acc-telemetry](https://github.com/blofelds/acc-telemetry): explain why, preserve the journey, progressive disclosure. Content is **honest to Slice 1** — stubs grow as features land; we do not invent filler for unbuilt slices.

## Start Here

1. **[../README.md](../README.md)** — Product overview, mock/V4L2 quick start, sessions + metrics
2. **[USER_GUIDE.md](USER_GUIDE.md)** — Running the service and starting sessions today
3. **[FEATURES.md](FEATURES.md)** — What exists vs what is planned

## Core documentation

### For users

- **[USER_GUIDE.md](USER_GUIDE.md)** — Install, mock capture, phone session UI, CSV location
- **[FEATURES.md](FEATURES.md)** — Slice 0–1 capabilities and roadmap boundaries
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Capture, bind, and metrics issues

### For developers

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Process shape, profiles, session CSV model
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** — Orientation for new contributors

## Specialized topics

None yet. Candidates as slices land:

- Capture device notes / known-good SKUs (after hardware validation)
- ROI / OCR pack format (Slice 2+)
- Prometheus / Grafana consumers (Slice 3+)
- CSV → SQLite migration notes (Slice 5)

## Historical / deprecated

Nothing deprecated yet. Slice 0 capture-tied session stubs were replaced by API-owned sessions in Slice 1 (documented in [FEATURES.md](FEATURES.md) journey notes).

## Quick reference (“I want to…”)

| Goal | Where |
| --- | --- |
| Run without hardware | [USER_GUIDE.md](USER_GUIDE.md) · mock backend |
| Start a session from phone | `http://<host>:8741/` · [USER_GUIDE.md](USER_GUIDE.md) |
| List sessions via API | `GET /api/sessions` · [FEATURES.md](FEATURES.md) |
| Scrape Prometheus | `GET /metrics` · [FEATURES.md](FEATURES.md) |
| Understand Pi 2B caps | [ARCHITECTURE.md](ARCHITECTURE.md) · `pi2b` profile |
| Fix hung `pip install` / uvloop on 2B | [TROUBLESHOOTING.md](TROUBLESHOOTING.md) · root README Pi 2B notes |
| Install as a service | [`../deploy/ac-telemetry.service`](../deploy/ac-telemetry.service) |

## Documentation philosophy

1. Preserve the journey — what was tried, what worked, why
2. Explain the why, not only the how
3. Keep historical material; mark status, don’t erase
4. Progressive disclosure — user guides first, architecture next
5. Practical focus — real commands and failure modes
6. Keep this index current when adding or retiring topics

## Contributing to docs

- Link new pages from this index and from the root README when user-facing
- Prefer expanding real content over inventing filler for unbuilt features
- Mark speculative or future sections clearly

## Changelog (docs)

| Date | Change |
| --- | --- |
| 2026-09-26 | Pi 2B install: plain uvicorn / no uvloop hang note |
| 2026-09-24 | Slice 0 stubs: index + core user/dev docs |
