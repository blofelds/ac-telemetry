# AC Telemetry — Documentation Index

Documentation follows the same **layout philosophy** as [blofelds/acc-telemetry](https://github.com/blofelds/acc-telemetry): explain why, preserve the journey, progressive disclosure. Content is **honest to Slice 0** — stubs grow as features land; we do not invent filler for unbuilt slices.

## Start Here

1. **[../README.md](../README.md)** — Product overview, mock/V4L2 quick start, metrics table
2. **[USER_GUIDE.md](USER_GUIDE.md)** — Running the service today
3. **[FEATURES.md](FEATURES.md)** — What exists vs what is planned

## Core documentation

### For users

- **[USER_GUIDE.md](USER_GUIDE.md)** — Install, mock capture, LAN status UI, CSV location
- **[FEATURES.md](FEATURES.md)** — Slice 0 capabilities and roadmap boundaries
- **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)** — Capture, bind, and metrics issues

### For developers

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — Process shape, profiles, capture backends, CSV stub
- **[PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)** — Orientation for new contributors

## Specialized topics

None yet. Candidates as slices land:

- Capture device notes / known-good SKUs (after hardware validation)
- ROI / OCR pack format (Slice 2+)
- Prometheus / Grafana consumers (Slice 3+)
- CSV → SQLite migration notes (Slice 5)

## Historical / deprecated

Nothing deprecated yet. Future bug-fix writeups and abandoned designs stay here (marked historical), linked from this index — same rule as acc-telemetry.

## Quick reference (“I want to…”)

| Goal | Where |
| --- | --- |
| Run without hardware | [USER_GUIDE.md](USER_GUIDE.md) · mock backend |
| Scrape Prometheus | `GET /metrics` · [FEATURES.md](FEATURES.md) |
| Understand Pi 2B caps | [ARCHITECTURE.md](ARCHITECTURE.md) · `pi2b` profile |
| Install as a service | [`../deploy/ac-telemetry.service`](../deploy/ac-telemetry.service) |
| See product plan (Project store) | Coordinator docs: plan / product brief (not in this repo yet) |

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
| 2026-09-24 | Slice 0 stubs: index + core user/dev docs |
