# Stint LAST accuracy (optional)

Session-scoped tooling to push LAST accuracy **over 99%** by reviewing **every
lap** (not only mismatches):

1. **ROI tee** — tiny `lap_time` crops at detect FPS (JPEG sequence by default)
2. **OCR sample log** — every detect read (timestamp + raw text)
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
| `roi/*.jpg` | Timestamped ROI crops (`seq_monoMs.jpg`) |
| `roi_manifest.jsonl` | seq + mono/wall + OCR text + path |
| `ocr_samples.jsonl` | Every detect sample |
| `gt.json` | Confirmed GT list |
| `score.json` / `score.md` | write% + ocr-sample% summary |
| `review.md` | **Every** GT lap: CSV write, OCR histogram, ROI paths |

### Metrics

| Metric | Definition |
| --- | --- |
| **write%** | Exact CSV LAST matches / GT laps (extras & misses reported separately) |
| **ocr-sample%** | Samples equal to that lap’s GT in the hold window / samples in window; also rolled up stint-wide |

Mismatches are marked ❌ in Markdown; matches still get a full review row so you
can chase the last fraction of a percent toward >99%.

## Remove the feature entirely

One rip-out later:

1. Delete package `ac_telemetry/accuracy/`
2. Delete YAML block `accuracy:` in `config/default.yaml`
3. Delete `AccuracySettings` / `Settings.accuracy` / `_parse_accuracy` in `ac_telemetry/settings.py`
4. Delete thin wiring:
   - `main.py` — lazy `maybe_accuracy_session` block + accuracy arg to `_stop_workers`
   - `api/__init__.py` — `accuracy=` param, session start/end hooks, `mount_accuracy_routes`
   - `detect/service.py` — `on_sample` field + `_emit_sample` (optional to keep as a generic hook)
5. Delete `docs/STINT_ACCURACY.md` and this guide’s links in FEATURES/USER_GUIDE
6. Delete `tests/test_accuracy_*.py`

Core lap detect/CSV must not import `ac_telemetry.accuracy` after that.
