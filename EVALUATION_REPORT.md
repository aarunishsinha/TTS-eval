# TTS Engine Objective Evaluation: Sarvam vs Smallest AI

This report provides the objective intelligibility comparison (Character Error Rate, or CER) and latency (Time To First Audio byte, TTFA) between **Sarvam** (`shubh` on `bulbul:v3`) and **Smallest AI** (`meher` on `lightning_v3.1_pro`) on the 69 Hinglish sentences in the evaluation set. Lower CER indicates higher intelligibility, and lower TTFA indicates faster response times.

## Summary of Results

Overall, **Smallest AI outperformed Sarvam** in nearly every category, with particularly strong improvements in edge cases, numbers, and navigation. Furthermore, Smallest AI achieved faster synthesis latency (TTFA) across the board.

### Latency (Time To First Audio Byte)

We recently migrated the testing harness from standard HTTP requests to **WebSockets** to bypass artificial network and python `requests` buffering (which previously waited for 4KB of data before yielding the first chunk). 

Here are the side-by-side comparisons of the **Old Baseline (HTTP)** vs **New Baseline (WebSockets)**:

| Provider / Voice | Protocol | P50 (Median) | P90 / P95 | P99 |
| :--- | :--- | :--- | :--- | :--- |
| **Smallest** (`meher`) | **WebSockets (New)** | **381 ms** | **579 ms** *(p90)* | **1190 ms** |
| **Smallest** (`meher`) | HTTP Streaming (Old) | 656 ms | 1044 ms *(p95)* | 1571 ms |
| | | | | |
| **Sarvam** (`shubh`) | **WebSockets (New)** | **552 ms** | **1286 ms** *(p90)* | **5964 ms** *(max)* |
| **Sarvam** (`shubh`) | HTTP Post (Old) | 892 ms | 1312 ms *(p95)* | 1831 ms |

> [!TIP]
> **Latency Takeaways:**
> Moving to WebSockets completely transformed the TTFA landscape. Smallest AI's median latency dropped from ~650ms to **381ms**, and Sarvam's dropped from ~900ms to **552ms**. These numbers are true real-time streaming TTFA, accurately representing the user-perceived delay before the first syllable is heard.

### CER by Category (Lower is Better)

*Note: The CER scores reflect the latest WebSocket synthesis pipeline. Minor fluctuations from the HTTP baseline are expected due to non-deterministic generational artifacts across runs.*

| Category | Sarvam (`shubh`) Mean CER | Smallest (`meher`) Mean CER | Winner |
| :--- | :--- | :--- | :--- |
| **Climate** | 0.249 | **0.229** | Smallest |
| **Conversational** | 0.297 | **0.261** | Smallest |
| **Edge** | 1.106 | **0.428** | Smallest |
| **Errors** | **0.257** | 0.298 | Sarvam |
| **Long** | 0.307 | **0.208** | Smallest |
| **Manual** | 0.200 | **0.189** | Smallest |
| **Media** | **0.247** | 0.250 | Tie / Sarvam |
| **Navigation** | 0.322 | **0.265** | Smallest |
| **Numbers** | 0.420 | **0.367** | Smallest |
| **Phone** | **0.150** | 0.167 | Sarvam |
| **Status** | **0.326** | 0.383 | Sarvam |
| **Windows** | 0.245 | **0.226** | Smallest |

> [!TIP]
> **Key Takeaway**: Smallest AI (`meher`) is significantly better at handling difficult Hinglish code-switching, edge cases (short utterances), and domain-specific vocabulary like numbers and navigation.

## Analysis of Errors

Both models struggled with extreme code-switching and numbers, but Sarvam exhibited more severe breakdown on edge cases.

### Common Failure Modes
1. **Numbers & Digits:** Both models often pronounce digits in Hindi instead of English or hallucinate pronunciations. 
    - e.g., `Aapki EMI 12` was heard as `आपकी ये माई बराज` (Sarvam).
2. **Short Utterances (Edge Cases):** 
    - `22.5` was completely butchered by Sarvam (`भाईस्पॉंट पाच।`) resulting in an extreme CER of 4.000. Smallest handled this perfectly.
    - Single words like `OK.` and `Toh?` caused high CER for both due to ASR hallucination or poor prosody on 1-word audio files.

### Worst Performing Sentences

| Model | ID | Reference Text | Transcribed Text | CER |
| :--- | :--- | :--- | :--- | :--- |
| **Sarvam** | `EDG-04` | 22.5 | भाईस्पॉंट पाच। | 4.000 |
| **Sarvam** | `EDG-02` | OK. | Okay. | 1.000 |
| **Smallest** | `EDG-02` | OK. | Okay. | 1.000 |
| **Sarvam** | `NUM-05` | Booking reference AB 7 7 4 2 K hai. | बुकिंग रिफरंसे भी साथ साथ चार दोके है। | 0.939 |
| **Sarvam** | `EDG-05` | Hmm... theek hai. | हुँ। चीचे। | 0.750 |
| **Smallest**| `NUM-03` | Trip meter 1 | ट्रिप मीटर यूंग। | 0.750 |

## Next Steps
- **Subjective Naturalness Testing**: The local A/B server is running at `http://localhost:8080/listen.html`. Do a blind test between the two to see which one *sounds* more natural, as CER only measures intelligibility, not human-like prosody!
