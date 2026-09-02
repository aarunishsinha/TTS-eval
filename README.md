# Hinglish TTS evaluation kit

A harness for deciding which text-to-speech engine to put in an in-car
assistant for the Indian market — and, later, for measuring how far behind
your offline fallback is.

## Why this exists before any vendor decision

Every TTS vendor publishes benchmarks in which they win. None of them
benchmark on Bengaluru street names, Hinglish command confirmations, or
lakh-grouped digits, because that isn't their market — it's yours. Until you
have your own eval set, you are choosing a vendor on marketing copy.

The kit measures two things that must be measured separately:

- **Intelligibility**, objectively, by roundtripping synthesized audio through
  an ASR and computing character error rate. This catches wrong digits,
  mangled place names, skipped words — the failures that break a car.
- **Naturalness**, subjectively, through a blind A/B listening test. There is
  no automated substitute for this. Anyone who tells you otherwise is selling
  a metric.

A voice can score perfectly on the first and still sound like a robot. A voice
can sound gorgeous and say "twenty-two" as "two two". You need both numbers.

## Setup

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # then fill in your API keys
export $(grep -v '^#' .env | xargs)
```

You need at least one API key to run synthesis. Free tiers:
- **Sarvam**: 1,000 credits → [sarvam.ai](https://sarvam.ai)
- **Smallest**: $10 credit → [smallest.ai](https://smallest.ai)
- **ElevenLabs** (optional, Western control arm) → [elevenlabs.io](https://elevenlabs.io)

Both Indian vendors change their API surface faster than any script can track.
If `synth.py` 400s, open their current docs and fix the request body — the
endpoint details in the provider functions are a starting point, not gospel.

## Run

```bash
# render the eval set with two or more arms
python synth.py --provider sarvam   --voice anushka
python synth.py --provider smallest --voice raman

# objective scoring
python score.py --model large-v3

# subjective scoring
python -m http.server 8000
# then open http://localhost:8000/listen.html
```

Start with `--only nav,numbers` if you want a fast first signal. Navigation
and numbers are where generic multilingual engines fall over, so they
discriminate between vendors with the fewest samples.

## Files

| File | What it does |
|---|---|
| `eval_sentences.csv` | ~70 car-domain utterances across 11 categories, in Roman, Devanagari, and mixed script |
| `synth.py` | Renders the set per provider/voice, records time-to-first-audio, writes `out/manifest.json` |
| `score.py` | ASR roundtrip → CER, broken down by provider and category |
| `listen.html` | Blind pairwise preference test, vendor labels hidden, exports `results.csv` |

## Reading the output

**The aggregate CER is the least useful number.** What you want is the
per-category breakdown. If a vendor is fine everywhere except `navigation`,
that's a pronunciation-dictionary problem and both Sarvam and Smallest let you
supply one — fixable in an afternoon. If it's bad on `conversational` and
`long`, that's the model's prosody and no amount of tuning saves it.

**Your ASR has its own error rate.** A nonzero CER is a ceiling, not a
measurement of the TTS alone. Record a human reading twenty of these sentences
and score those too — whatever CER the human gets is your noise floor.

**Latency from your desk is not latency from a car.** Rerun `synth.py`
tethered to a phone while someone else drives a normal route, and compare the
p90 and p99 against the desk numbers. The gap between those two runs is the
single most important number in this whole exercise, because it determines how
much work your offline tier has to do.

## Extending the sentence set

The set here is a skeleton sized for one evening of listening. Grow it from
real usage, not imagination: log what your assistant actually says, sample the
long tail, and add the utterances that broke. An eval set that doesn't grow
after every failure isn't an eval set, it's a ritual.

Categories worth adding once the basics hold: regional accents beyond the
Hindi belt, in-cabin noise (synthesize, then mix road noise at 65–75 dB before
scoring — a voice that's intelligible in a quiet room can vanish at 100 km/h),
and interruption behaviour at chunk boundaries if you're streaming.

## Adding your offline arm

`synth.py` providers are just functions returning `(wav_bytes, ttfa_ms)`. When
you get to the local tier, add one for Kokoro or whatever you land on, render
the same sentences, and put it in the same blind test as the cloud arms.
Knowing that your fallback loses 70/30 to Sarvam is useful. Knowing it loses
95/5 tells you it isn't shippable yet.
