#!/usr/bin/env python3
"""
Render eval_sentences.csv across multiple TTS providers, saving one WAV per
sentence per voice and recording time-to-first-audio.

    pip install requests
    export SARVAM_API_KEY=...  SMALLEST_API_KEY=...
    python synth.py --provider sarvam --voice anushka
    python synth.py --provider smallest --voice raman

Output:
    out/<provider>/<voice>/<id>.wav
    out/manifest.json      (accumulated across runs; consumed by listen.html)

Adding a provider means writing one function that returns (wav_bytes, ttfa_ms)
and registering it in PROVIDERS. Nothing else changes.
"""

import argparse
import csv
import json
import os
import sys
import time
import base64
import asyncio
import ssl
import certifi
import wave
import io
from pathlib import Path

import requests
import websockets

OUT = Path("out")
MANIFEST = OUT / "manifest.json"
TIMEOUT = 60


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
# Each returns (wav_bytes, ttfa_ms).
#
# ttfa_ms here is time-to-first-audio-byte measured with streaming requests.
# On a non-streaming endpoint it degenerates to full round-trip time, which is
# NOT comparable across providers -- so prefer the streaming path where the
# vendor offers one. Where a provider's streaming API is a WebSocket, the HTTP
# number below is an upper bound; go back and measure the socket properly
# before you make a decision on latency.


def synth_sarvam(text, voice, api_key):
    """Sarvam Bulbul v3 via WebSockets for true TTFA streaming.
    Available v3 voices: shubh, aditya, ritu, priya, neha, rahul, pooja,
    rohan, simran, kavya, amit, dev, ishita, shreya, and ~25 more.
    Note: v2 voices (anushka, manisha, etc.) do NOT work with v3."""
    async def _run():
        t0 = time.perf_counter()
        uri = "wss://api.sarvam.ai/text-to-speech/ws"
        headers = {"Api-Subscription-Key": api_key}
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ttfa = None
        chunks = []
        async with websockets.connect(uri, additional_headers=headers, ssl=ssl_context) as ws:
            # Send configuration
            await ws.send(json.dumps({
                "type": "config",
                "data": {
                    "language_code": "hi-IN",
                    "speaker": voice,
                    "model": "bulbul:v3"
                }
            }))
            # Send text payload
            await ws.send(json.dumps({
                "type": "text",
                "data": {"text": text}
            }))
            # Force generation with flush
            await ws.send(json.dumps({"type": "flush"}))
            
            try:
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    except asyncio.TimeoutError:
                        break  # Assume generation is complete if no data for 2 seconds
                        
                    try:
                        data = json.loads(msg)
                    except json.JSONDecodeError:
                        continue
                    
                    if data.get("type") == "audio":
                        if ttfa is None:
                            ttfa = (time.perf_counter() - t0) * 1000
                        audio_b64 = data.get("data", {}).get("audio", "")
                        if audio_b64:
                            chunks.append(base64.b64decode(audio_b64))
                    elif data.get("type") == "completion":
                        break
            except Exception as e:
                print(f"Sarvam WS Error: {e}", file=sys.stderr)
        return b"".join(chunks), ttfa or 0.0

    return asyncio.run(_run())


def synth_smallest(text, voice, api_key):
    """Smallest.ai Lightning v3.1 via WebSockets for true TTFA streaming.
    Note: v2 voices (like raman) are deprecated. Use 'meher' or 'aviraj' (Pro pool)
    or 'devansh' or 'sunidhi' (Standard pool)."""
    async def _run():
        t0 = time.perf_counter()
        model = "lightning_v3.1_pro" if voice in ["meher", "aviraj"] else "lightning_v3.1"
        uri = f"wss://api.smallest.ai/waves/v1/lightning-v3.1/get_speech/stream?api_key={api_key}"
        ssl_context = ssl.create_default_context(cafile=certifi.where())
        ttfa = None
        chunks = []
        async with websockets.connect(uri, ssl=ssl_context) as ws:
            payload = {
                "text": text,
                "voice_id": voice,
                "sample_rate": 24000,
                "output_format": "wav",
                "model": model,
            }
            await ws.send(json.dumps(payload))
            
            try:
                while True:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    except asyncio.TimeoutError:
                        break # Assume generation is complete if no data for 2 seconds
                        
                    if isinstance(message, bytes):
                        if ttfa is None:
                            ttfa = (time.perf_counter() - t0) * 1000
                        chunks.append(message)
                    elif isinstance(message, str):
                        try:
                            event = json.loads(message)
                            if event.get("event") == "end_of_audio" or event.get("type") == "end_of_audio":
                                break
                            
                            # Check if the JSON contains audio data
                            data_field = event.get("data")
                            if isinstance(data_field, dict):
                                audio_data = data_field.get("audio")
                            else:
                                audio_data = event.get("audio")
                                
                            if audio_data and isinstance(audio_data, str):
                                if ttfa is None:
                                    ttfa = (time.perf_counter() - t0) * 1000
                                chunks.append(base64.b64decode(audio_data))
                        except json.JSONDecodeError:
                            pass
            except Exception as e:
                print(f"Smallest WS Error: {e}", file=sys.stderr)
                
        pcm_data = b"".join(chunks)
        if not pcm_data:
            return b"", 0.0
            
        wav_io = io.BytesIO()
        with wave.open(wav_io, 'wb') as wav_file:
            wav_file.setnchannels(1) # mono
            wav_file.setsampwidth(2) # 16-bit
            wav_file.setframerate(24000)
            wav_file.writeframes(pcm_data)
            
        return wav_io.getvalue(), ttfa or 0.0

    return asyncio.run(_run())


def synth_elevenlabs(text, voice, api_key):
    """ElevenLabs, as a Western-flagship control arm. Not a serious candidate
    for Hinglish, but you want the comparison in your listening test so you
    can see the gap rather than take my word for it."""
    t0 = time.perf_counter()
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/stream",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={"text": text, "model_id": "eleven_flash_v2_5",
              "output_format": "pcm_24000"},
        stream=True,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    chunks, ttfa = [], None
    for chunk in r.iter_content(chunk_size=4096):
        if chunk:
            if ttfa is None:
                ttfa = (time.perf_counter() - t0) * 1000
            chunks.append(chunk)
    return b"".join(chunks), ttfa or 0.0


def synth_google(text, voice, api_key):
    """Google Cloud TTS with Chirp 3 HD voices via service account auth.

    Setup:
      1. Enable Cloud Text-to-Speech API in your GCP project
      2. Create a Service Account, download the JSON key
      3. Set GOOGLE_TTS_SA_KEY to the path of that JSON file

    Voice names follow the pattern: hi-IN-Chirp3-HD-<variant>
    Use --voice with just the variant part, e.g. 'Charon' or 'Leda'.
    If unsure, list voices after auth is set up:
      curl -H "Authorization: Bearer $(gcloud auth print-access-token)" \\
        "https://texttospeech.googleapis.com/v1/voices?languageCode=hi-IN"
    """
    from google.oauth2 import service_account
    from google.auth.transport.requests import Request

    # api_key here is the path to the service account JSON file
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    creds = service_account.Credentials.from_service_account_file(
        api_key, scopes=scopes)
    creds.refresh(Request())

    # Build the full voice name if user passed just the variant
    if not voice.startswith("hi-IN"):
        full_voice = f"hi-IN-Chirp3-HD-{voice}"
    else:
        full_voice = voice

    t0 = time.perf_counter()
    r = requests.post(
        "https://texttospeech.googleapis.com/v1/text:synthesize",
        headers={"Authorization": f"Bearer {creds.token}",
                 "Content-Type": "application/json"},
        json={
            "input": {"text": text},
            "voice": {
                "languageCode": "hi-IN",
                "name": full_voice,
            },
            "audioConfig": {
                "audioEncoding": "LINEAR16",
                "sampleRateHertz": 24000,
            },
        },
        timeout=TIMEOUT,
    )
    ttfa = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    payload = r.json()
    audio_b64 = payload["audioContent"]
    return base64.b64decode(audio_b64), ttfa


PROVIDERS = {
    "sarvam":     (synth_sarvam,     "SARVAM_API_KEY"),
    "smallest":   (synth_smallest,   "SMALLEST_API_KEY"),
    "elevenlabs": (synth_elevenlabs, "ELEVENLABS_API_KEY"),
    "google":     (synth_google,     "GOOGLE_TTS_SA_KEY"),
}


# --------------------------------------------------------------------------

def load_manifest():
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"sentences": {}, "renders": []}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", required=True, choices=PROVIDERS)
    ap.add_argument("--voice", required=True,
                    help="provider-specific voice id")
    ap.add_argument("--csv", default="eval_sentences.csv")
    ap.add_argument("--only", default=None,
                    help="comma-separated categories, e.g. nav,numbers")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    fn, env_var = PROVIDERS[args.provider]
    api_key = os.environ.get(env_var)
    if not api_key:
        sys.exit(f"Set {env_var} in your environment.")

    rows = list(csv.DictReader(open(args.csv, encoding="utf-8")))
    if args.only:
        wanted = {c.strip().lower() for c in args.only.split(",")}
        rows = [r for r in rows if r["category"].lower() in wanted]
    if args.limit:
        rows = rows[:args.limit]

    dest = OUT / args.provider / args.voice
    dest.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest()

    latencies, failures = [], []
    for i, row in enumerate(rows, 1):
        sid = row["id"]
        path = dest / f"{sid}.wav"
        if path.exists():
            print(f"[{i}/{len(rows)}] {sid} cached")
            continue
        try:
            audio, ttfa = fn(row["text"], args.voice, api_key)
            path.write_bytes(audio)
            latencies.append(ttfa)
            print(f"[{i}/{len(rows)}] {sid:10s} {ttfa:7.0f} ms  "
                  f"{len(audio)/1024:6.1f} KB")
        except Exception as e:
            failures.append((sid, repr(e)))
            print(f"[{i}/{len(rows)}] {sid:10s} FAILED  {e}")
            continue

        manifest["sentences"][sid] = {
            "text": row["text"],
            "category": row["category"],
            "variant": row["variant"],
            "tests": row["tests"],
        }
        manifest["renders"].append({
            "id": sid,
            "provider": args.provider,
            "voice": args.voice,
            "path": f"{args.provider}/{args.voice}/{sid}.wav",
            "ttfa_ms": round(ttfa, 1),
        })

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

    if latencies:
        latencies.sort()
        p = lambda q: latencies[min(int(len(latencies) * q), len(latencies) - 1)]
        print(f"\n{args.provider}/{args.voice}  n={len(latencies)}")
        print(f"  p50 {p(0.50):6.0f} ms")
        print(f"  p90 {p(0.90):6.0f} ms")
        print(f"  p99 {p(0.99):6.0f} ms")
        print(f"  max {latencies[-1]:6.0f} ms")
    if failures:
        print(f"\n{len(failures)} failures:")
        for sid, err in failures:
            print(f"  {sid}: {err}")


if __name__ == "__main__":
    main()
