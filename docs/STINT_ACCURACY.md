# Stint LAST accuracy (optional)

Session-scoped tooling to push LAST accuracy **over 99%** by reviewing **every
lap** (not only mismatches):

1. **ROI tee** — tiny `lap_time` crops for review (JPEG sequence by default),
   capped at **3 per hold** (see below)
2. **OCR sample log** — every detect read (timestamp + raw text) at **full
   detect rate** (unaffected by the JPEG cap)
3. **GT scores** — after the stint, confirm a ground-truth lap list → **write%**
   and **ocr-sample%** plus a per-lap review

**Default: off.** Core LAST detect/CSV behaviour is unchanged when disabled.

## Disable (runtime)

Keep the YAML default, or force off:

```yaml
accuracy:
  enabled: false
```

```bash
export AC_TELEMETRY_ACCURACY_ENABLED=0
```

When disabled:

- `ac_telemetry.accuracy` is **not imported** at process start
- detect `on_sample` hook is `None` (no per-tick cost beyond a null check)
- no `/api/accuracy/*` routes
- no ROI files or OCR JSONL

## Enable for an accuracy stint

```yaml
accuracy:
  enabled: true
  with_session: true          # start/stop with phone session
  roi_tee: true
  ocr_log: true
  roi_tee_format: jpeg_seq    # preferred on Pi 2B
  roi_tee_max_per_hold: 3     # JPEG cap per stable LAST hold; 0 = unlimited
```

```bash
export AC_TELEMETRY_ACCURACY_ENABLED=1
# restart ac-telemetry
```

### Stint → GT → scores

```bash
PI="${PI:-http://127.0.0.1:8741}"

# 1) Start a session (tee + OCR log start automatically when with_session)
curl -sS -X POST "$PI/api/sessions" -H 'Content-Type: application/json' \
  -d '{"track":"Monza","car":"…","notes":"accuracy stint"}'

# 2) Drive the stint…

# 3) End session (stops tee/log)
curl -sS -X POST "$PI/api/sessions/current/end"
SESSION_ID=…   # from the JSON, or GET /api/sessions

# 4) Prefill GT from CSV, edit, confirm
curl -sS "$PI/api/accuracy/sessions/$SESSION_ID/gt/prefill" -o /tmp/gt_draft.json
# edit laps[] to the true HUD LAST sequence, then:
curl -sS -X POST "$PI/api/accuracy/sessions/$SESSION_ID/gt" \
  -H 'Content-Type: application/json' \
  -d @"/tmp/gt_draft.json"
```

#### GT eyeballing helper (phone / browser)

When accuracy is enabled, open:

```text
http://<pi>:8741/accuracy
http://<pi>:8741/accuracy/<session_id>
```

(`?session=<id>` also works on `/accuracy`.) Routes **404** when
`accuracy.enabled` is false.

Layout: **two tee crops on the left** per lap (first + last of that hold’s
JPEG tee; or both when only two exist), **editable lap times + mark
(normal / double / skip) on the right**. Per-row **Insert skip after** adds a
GT-only skip row (`mark=skip`, no CSV ref, empty time) immediately after that
row — use this when the HUD showed a lap the CSV missed between two writes.
**Add skip lap** still appends a skip at the end of the list. Per-row **skip**
is disabled when the row already has a `csv_lap_number` (a false extra CSV
write is **double**, not skip). **Confirm** still requires a non-empty
`M:SS.mmm` on every row (including skips) and calls
`POST /api/accuracy/sessions/{id}/gt/confirm`, which:

1. Writes `gt_draft.json` and `gt.json` (including per-row `mark`) under the
   accuracy session dir
2. Sets `note=gt_confirmed` on session rows in `laps.csv`
3. Updates `lap_time` / `lap_time_ms` on CSV rows tied to normal/double marks
4. Scores write% / ocr-sample% with doubles/skips applied (see Marks below)

Page data: `GET /api/accuracy/sessions/{id}/helper` (laps + crop URLs + marks).
Crops: `GET /api/accuracy/sessions/{id}/roi/{filename}.jpg`.

##### Marks (double / skip)

| Mark | Meaning | write% | extras / misses |
| --- | --- | --- | --- |
| **normal** | True on-screen lap that should match a CSV write | In denom; match → numerator | Unmatched → miss |
| **double** | False extra CSV write (OCR double / flicker) | **Excluded** from denom and numerator; still annotated in `score.md` / `review.md` | CSV consumed — **not** an unexplained extra |
| **skip** | On-screen lap with **no** CSV write | In denom; never matches | Always a **miss**; allows a GT row without a CSV ref |

Persisted on each lap in `gt_draft.json` / `gt.json` as `"mark": "normal"|"double"|"skip"`.

##### Two-layer accuracy model

Accuracy tracking is intentionally two layers (this helper is the second):

1. **CI ROI fixtures (later)** — small, replayable crops/holds for fast
   before/after scores on PRs. Not the merge-of-record for a full stint.
2. **Full-video / full-stint merge-of-record** — operator Confirm on
   `/accuracy/<session_id>` produces the GT + `score.md` that history and
   gates will treat as authoritative for that session (doubles/skips included).

(CI harness, history append, and PR gates are separate slices — not in this
helper change.)

Offline CLI (works even if runtime has accuracy off — scores stored artefacts):

```bash
python -m ac_telemetry.accuracy prefill "$SESSION_ID" -o gt_draft.json
# edit gt_draft.json
python -m ac_telemetry.accuracy gt "$SESSION_ID" gt_draft.json --score
# or: python -m ac_telemetry.accuracy score "$SESSION_ID"
```

### Where files land

Under `{data_dir}/accuracy/{session_id}/` (default `data/sessions/accuracy/<id>/`):

| File | Role |
| --- | --- |
| `roi/*.jpg` | Timestamped ROI crops (`seq_monoMs.jpg`), ≤3 per hold by default |
| `roi_manifest.jsonl` | seq + mono/wall + OCR text + path (tee’d frames only) |
| `ocr_samples.jsonl` | Every detect sample (full rate — drives ocr-sample%) |
| `gt_draft.json` | Helper Confirm draft (same laps as `gt.json`) |
| `gt.json` | Confirmed GT list |
| `score.json` / `score.md` | write% + ocr-sample% summary |
| `review.md` | **Every** GT lap: CSV write, OCR histogram, ROI paths |

### ROI tee density (per hold)

A **hold** is a run of consecutive detect samples with the same OCR text (the
last_lap stable-hold window while HUD LAST is unchanged). Operators can read
digits in virtually every crop, so hundreds of JPEGs per lap are unnecessary.

| Knob | Default | Meaning |
| --- | --- | --- |
| `accuracy.roi_tee_max_per_hold` | `3` | Max JPEG crops written per hold (`0` = unlimited) |

**Which 3 frames:** for each hold the tee keeps the **first**, **middle**
(`(n - 1) // 2`), and **last** sample. Shorter holds write fewer frames; other
cap values use endpoints plus even spacing.

**Unchanged by the cap:** `ocr_samples.jsonl` / the OCR log still records
**every** detect sample, so **write%** and **ocr-sample%** are unaffected.

### Metrics

| Metric | Definition |
| --- | --- |
| **write%** | Exact CSV LAST matches / scoring GT laps (**normal + skip**; **doubles excluded**). Extras = unexplained CSV; misses include skips. |
| **ocr-sample%** | Samples equal to that lap’s GT in the hold window / samples in window; also rolled up stint-wide (doubles omitted from the roll-up) |

Mismatches are marked ❌ in Markdown; doubles ◎ and skips ○ are annotated;
matches still get a full review row so you can chase the last fraction of a
percent toward >99%.

## Remove the feature entirely

One rip-out later:

1. Delete package `ac_telemetry/accuracy/`
2. Delete `ac_telemetry/web/accuracy.py` (helper HTML)
3. Delete YAML block `accuracy:` in `config/default.yaml`
4. Delete `AccuracySettings` / `Settings.accuracy` / `_parse_accuracy` in `ac_telemetry/settings.py`
5. Delete thin wiring:
   - `main.py` — lazy `maybe_accuracy_session` block + accuracy arg to `_stop_workers`
   - `api/__init__.py` — `accuracy=` param, session start/end hooks, `mount_accuracy_routes`
   - `detect/service.py` — `on_sample` field + `_emit_sample` (optional to keep as a generic hook)
6. Optionally drop the `note` column from `LapStore` / `laps.csv` if nothing else uses it
7. Delete `docs/STINT_ACCURACY.md` and this guide’s links in FEATURES/USER_GUIDE
8. Delete `tests/test_accuracy_*.py`

Core lap detect/CSV must not import `ac_telemetry.accuracy` after that.
