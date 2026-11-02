"""The words in a recording, for lip-sync transcripts (faster-whisper, free and local, on the CPU).

    python generate/transcribe.py FILE.wav [--model small.en]      prints the transcript

The app calls this when a voice performance is uploaded without its words. small.en is English only; pass
--model small for other languages (downloaded once).
"""
import sys

from faster_whisper import WhisperModel

model_name = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "small.en"
model = WhisperModel(model_name, device="cpu", compute_type="int8")
segments, _ = model.transcribe(sys.argv[1], beam_size=5, vad_filter=True)
print(" ".join(seg.text.strip() for seg in segments).strip())
