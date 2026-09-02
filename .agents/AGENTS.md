# TTS-eval — Agent Steering

## Project Overview

This is an evaluation harness for comparing text-to-speech engines on Hinglish
(Hindi-English code-mixed) utterances in an in-car assistant context. It is
**not** an application — it is a measurement tool.

The pipeline has three stages:

1. **Synthesise** (`synth.py`) — Render `eval_sentences.csv` through one or more
   TTS providers, writing WAV files to `out/<provider>/<voice>/` and accumulating
   metadata into `out/manifest.json`.
2. **Score objectively** (`score.py`) — Roundtrip each WAV through an ASR
   (faster-whisper), compute character error rate (CER) against the original
   text, and write `out/scores.csv`.
3. **Score subjectively** (`listen.html`) — Blind pairwise A/B listening test
   served over `python -m http.server`. Exports `results.csv`.

## Architecture

```
eval_sentences.csv   ← ~70 Hinglish utterances, 11 categories
        │
   synth.py --provider X --voice Y
        │
        ▼
  out/manifest.json  ← accumulated across runs
  out/<provider>/<voice>/<id>.wav
        │
   ┌────┴────┐
   ▼         ▼
score.py   listen.html
   │         │
   ▼         ▼
out/scores.csv  results.csv
```

## Key Conventions

### Provider pattern
Every TTS provider is a plain function with signature:
```python
def synth_<name>(text: str, voice: str, api_key: str) -> tuple[bytes, float]:
    """Returns (wav_bytes, ttfa_ms)."""
```
Registered in the `PROVIDERS` dict as `"name": (function, "ENV_VAR_NAME")`.
To add a new provider, write the function and add one line to `PROVIDERS`.
Nothing else changes.

### Output layout
All generated artifacts go under `out/`. This directory is gitignored.
- `out/<provider>/<voice>/<id>.wav` — synthesised audio
- `out/manifest.json` — accumulated metadata (consumed by `listen.html`)
- `out/scores.csv` — objective CER scores

### Secrets
API keys are read from environment variables, **never hardcoded**.
- Local development: copy `.env.example` to `.env` and fill in keys.
- The scripts read `os.environ` directly. If using `.env`, source it or use
  `export $(grep -v '^#' .env | xargs)` before running.

### Text normalisation (score.py)
Hinglish comparison requires collapsing Devanagari ↔ Roman script and spelling
variations (e.g. "kya" vs "kyaa" vs "क्या"). The `normalize()` function in
`score.py` handles this. Any changes to scoring must preserve this normalisation
or CER becomes meaningless.

## Dependencies

- **Runtime**: `requests`, `faster-whisper`, `indic-transliteration`, `jiwer`
- **Python**: 3.10+ (required by `faster-whisper`)
- **Install**: Always use the project venv (`.venv/`), never install globally.
  ```bash
  python3.12 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

## Rules

1. **Do not modify `eval_sentences.csv` schema.** The CSV columns (`id`,
   `category`, `variant`, `text`, `tests`) are consumed by all three stages.
   Adding columns is fine; renaming or removing breaks everything.

2. **Do not change the `out/manifest.json` format** without updating both
   `synth.py` (writer), `score.py` (reader), and `listen.html` (reader).

3. **Provider functions must be self-contained.** Each should handle its own
   HTTP call, error handling, and return the standard `(wav_bytes, ttfa_ms)`
   tuple. No shared HTTP sessions or global state.

4. **Keep the eval set honest.** Sentences should come from real usage, not
   imagination. See README § "Extending the sentence set".

5. **No unit tests exist yet.** Verification is done by running `synth.py` and
   `score.py` end-to-end with real API keys.

6. **Latency numbers from `synth.py` are informational, not comparable** across
   providers unless both use streaming. Read the docstring at the top of the
   providers section.

7. **The aggregate CER is the least useful number.** Always look at the
   per-category breakdown. See README § "Reading the output".
