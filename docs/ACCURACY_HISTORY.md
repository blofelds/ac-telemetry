# Accuracy history (full-video + future ROI CI)

Track LAST detect accuracy across merges without inventing a single number when
evidence conflicts.

## Two measurement layers

| Layer | What | When | Status |
| --- | --- | --- | --- |
| **Full-video** | Replay card_long master MKVs end-to-end through template OCR + `DetectService._handle_reading` | Masters available on disk (Cursor-hosted env or Latitude) | **This PR** — `scripts/replay_accuracy.py` |
| **ROI CI** (later) | Crop / hold fixtures derived from card_long + confirmed stints; cheap CI score | After fixture pack lands | **Not yet** — do not treat missing ROI CI as a full-video regression |

Full-video is the ground-truth-aligned offline proof for OCR/gate changes.
ROI fixtures are a faster advisory gate for PRs; they come later (no GitHub
Actions / Pages / fail-vs-main in this slice).

## History file

Path: [`accuracy/history.jsonl`](../accuracy/history.jsonl)

One JSON object per line, **one line per known merge** that has store evidence.
Append on merge to `main` only (policy); this seed backfills #25 / #31 / #32 / #33.

### Schema (fields)

| Field | Required | Meaning |
| --- | --- | --- |
| `pr` | yes | Pull request number |
| `commit` | when known | Merge commit on `main` (40-char SHA) |
| `tip_commit` | optional | Feature-branch tip SHA if useful |
| `dataset_id` | yes | e.g. `card_long_20261005` |
| `layer` | yes | `full_video` (or later `roi_ci`) |
| `videos` | yes | Per-video scores keyed by clip id (`20261005-123100`, …) |
| `overall_exact` | when known | e.g. `"11/13"` |
| `notes` | optional | Provenance / caveats |

### Per-video object

| Field | Meaning |
| --- | --- |
| `exact` / `expected` | Exact GT LAST strings present in writes / GT count |
| `written` | CSV write count |
| `extra` | Writes that are not exact GT strings |
| `missed` | GT strings never written |
| `gate` | Shorthand `written/extra/missed` when clean counting applies |
| `status` | Use `"unreconciled"` instead of a single `exact` when sources disagree |
| `citations` | Under `unreconciled`: list of `{commit, exact, expected, …, source}` |

**Unreconciled example:** PR #25 clip `124252` is recorded as **1/4** (early tip) vs
**0/4** (later tip) with both citations — do not collapse to one number.

## How to run the harness

```bash
# from repo root, venv active; masters on disk
python scripts/replay_accuracy.py
python scripts/replay_accuracy.py --video-dir ~/ac-telemetry-testdata/card_long
python scripts/replay_accuracy.py --only 123100 --json-out /tmp/card_long.json
```

Env override for the masters directory: `AC_TELEMETRY_CARD_LONG`.

Built-in GT covers the known 2026-10-05 / 2026-10-06 card_long ids used in prior
proofs. Unknown filenames still replay and print writes (no score).

## Related

- Session / stint ROI tee + GT helper: [STINT_ACCURACY.md](STINT_ACCURACY.md)
- Short MJPEG gate stress (not full masters): `scripts/replay_last_lap_clips.py`
