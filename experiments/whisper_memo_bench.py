"""WER + latency for faster-whisper models on real recorded memos (spec Task 9).

Usage:
  1. Record ~5 bench memos:  ytk memo records to ~/.ytk/audio/memos/; copy
     representative wavs into ~/.ytk/audio/memos/bench/
  2. For each bench wav, write a sibling .txt with the hand-corrected transcript.
  3. uv run python experiments/whisper_memo_bench.py
"""

import time
from pathlib import Path

BENCH_DIR = Path.home() / ".ytk" / "audio" / "memos" / "bench"
MODELS = ["base", "small", "distil-large-v3", "large-v3-turbo"]


def wer(ref: str, hyp: str) -> float:
    """Word error rate via Levenshtein distance on whitespace tokens."""
    r, h = ref.lower().split(), hyp.lower().split()
    d = list(range(len(h) + 1))
    for i in range(1, len(r) + 1):
        prev, d[0] = d[0], i
        for j in range(1, len(h) + 1):
            cur = min(
                d[j] + 1,  # deletion
                d[j - 1] + 1,  # insertion
                prev + (r[i - 1] != h[j - 1]),  # substitution
            )
            prev, d[j] = d[j], cur
    return d[len(h)] / max(len(r), 1)


def main():
    from faster_whisper import WhisperModel

    pairs = sorted(
        (wav, wav.with_suffix(".txt"))
        for wav in BENCH_DIR.glob("*.wav")
        if wav.with_suffix(".txt").exists()
    )
    if not pairs:
        raise SystemExit(
            f"No (wav, txt) pairs in {BENCH_DIR}. Record memos and write "
            "hand-corrected .txt references first."
        )
    print(f"{len(pairs)} bench memos\n")
    print(f"{'model':<18}{'WER':>8}{'load s':>9}{'xRT':>7}")

    for name in MODELS:
        t0 = time.perf_counter()
        model = WhisperModel(name, device="cpu", compute_type="int8")
        load_s = time.perf_counter() - t0

        total_wer, total_audio, total_time = 0.0, 0.0, 0.0
        for wav, txt in pairs:
            t0 = time.perf_counter()
            segments, info = model.transcribe(str(wav))
            hyp = " ".join(s.text.strip() for s in segments).strip()
            total_time += time.perf_counter() - t0
            total_audio += info.duration
            total_wer += wer(txt.read_text().strip(), hyp)

        xrt = total_time / max(total_audio, 0.1)  # transcribe-time per audio-second
        print(f"{name:<18}{total_wer / len(pairs):>8.3f}{load_s:>9.1f}{xrt:>7.2f}")


if __name__ == "__main__":
    main()
