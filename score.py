#!/usr/bin/env python3
"""
Objective intelligibility scoring for the rendered eval set.

The idea: if a good ASR can't recover what the TTS was asked to say, the TTS
mispronounced it. This catches the failures that matter most in a car --
wrong digits, mangled place names, skipped words -- and it is the only part
of TTS evaluation you can automate honestly. Naturalness still needs ears.

    pip install faster-whisper jiwer indic-transliteration
    python score.py --model large-v3

Writes out/scores.csv and prints a per-provider, per-category breakdown.

A caveat you should internalise rather than paper over: your ASR has its own
Hinglish error rate, so a nonzero CER here is a *ceiling*, not a measurement
of the TTS alone. Sanity-check it by scoring real human recordings of the same
sentences -- whatever CER those get is your noise floor. Anything at or below
that floor is indistinguishable from human, as far as this metric can tell.
"""

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

OUT = Path("out")


# --------------------------------------------------------------------------
# Normalisation
# --------------------------------------------------------------------------
# Hinglish comparison is meaningless without collapsing script and spelling
# variation first. "kya", "kyaa" and "क्या" are the same word; scoring them as
# different is measuring your orthography, not your TTS.

try:
    from indic_transliteration import sanscript
    from indic_transliteration.sanscript import transliterate
    HAVE_INDIC = True
except ImportError:
    HAVE_INDIC = False


def to_common_script(s):
    """Fold everything to lowercase Latin so Devanagari and Roman compare."""
    if HAVE_INDIC and re.search(r"[\u0900-\u097F]", s):
        s = transliterate(s, sanscript.DEVANAGARI, sanscript.ITRANS)
    return s.lower()


def normalize(s):
    s = unicodedata.normalize("NFC", s)
    s = to_common_script(s)
    s = re.sub(r"[^\w\s]", " ", s)          # drop punctuation
    s = re.sub(r"\s+", " ", s).strip()
    # collapse doubled vowels: kyaa -> kya, hain -> hain (leaves consonants)
    s = re.sub(r"([aeiou])\1+", r"\1", s)
    return s


def cer(ref, hyp):
    """Character error rate via Levenshtein. Small inputs, so the naive DP
    is fine and avoids a dependency."""
    ref, hyp = normalize(ref), normalize(hyp)
    if not ref:
        return 0.0 if not hyp else 1.0
    prev = list(range(len(hyp) + 1))
    for i, rc in enumerate(ref, 1):
        cur = [i]
        for j, hc in enumerate(hyp, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1,
                           prev[j - 1] + (rc != hc)))
        prev = cur
    return prev[-1] / len(ref)


# --------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="large-v3",
                    help="faster-whisper model size")
    ap.add_argument("--language", default="hi")
    args = ap.parse_args()

    from faster_whisper import WhisperModel
    asr = WhisperModel(args.model, device="auto", compute_type="auto")

    manifest = json.loads((OUT / "manifest.json").read_text())
    sentences = manifest["sentences"]

    rows = []
    for r in manifest["renders"]:
        wav = OUT / r["path"]
        if not wav.exists():
            continue
        segments, _ = asr.transcribe(str(wav), language=args.language,
                                     beam_size=5)
        hyp = " ".join(seg.text for seg in segments)
        ref = sentences[r["id"]]["text"]
        rows.append({
            "id": r["id"],
            "provider": r["provider"],
            "voice": r["voice"],
            "category": sentences[r["id"]]["category"],
            "variant": sentences[r["id"]]["variant"],
            "ttfa_ms": r["ttfa_ms"],
            "reference": ref,
            "heard": hyp.strip(),
            "cer": round(cer(ref, hyp), 4),
        })
        print(f"{r['id']:10s} {r['provider']:11s} cer={rows[-1]['cer']:.3f}")

    with open(OUT / "scores.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    # Breakdown -- the aggregate number is the least interesting output here.
    # What you want is which categories a vendor fails, because that tells you
    # whether the failure is fixable with a pronunciation dictionary.
    by = defaultdict(list)
    for r in rows:
        by[(r["provider"], r["voice"], r["category"])].append(r["cer"])

    print("\nCER by provider and category (lower is better)")
    print(f"{'provider/voice':28s} {'category':14s} {'n':>3s} {'mean':>7s} {'worst':>7s}")
    for (prov, voice, cat), vals in sorted(by.items()):
        print(f"{prov + '/' + voice:28s} {cat:14s} {len(vals):3d} "
              f"{sum(vals)/len(vals):7.3f} {max(vals):7.3f}")

    print("\nWorst 15 individual sentences:")
    for r in sorted(rows, key=lambda r: -r["cer"])[:15]:
        print(f"  {r['cer']:.3f}  {r['provider']:10s} {r['id']:8s} {r['reference'][:60]}")
        print(f"         heard: {r['heard'][:70]}")


if __name__ == "__main__":
    main()
