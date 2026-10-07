# local_market_analysis_v2.py
#
# TWO-PASS MAP-REDUCE approach:
#
# PASS 1 — MAP:
#   Split transcript into chunks
#   For each chunk → LLM produces a crisp mini-summary
#   All mini-summaries compiled into one intermediate file
#
# PASS 2 — REDUCE:
#   Read the compiled summaries file
#   Chunk again if still too large (rare, since summaries are short)
#   LLM reads all summaries and produces FINAL report:
#     - Unique key points + their market effect
#     - Sectors going DOWN (with reason)
#     - Sectors going UP (with reason)
#     - Sentiment Analysis (Bullish / Bearish / Neutral + reasoning)
#
# Install:
#   sudo apt install build-essential cmake
#   CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir
#   pip install huggingface-hub
#
# Download model (one time, ~4.4GB):
#   huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \
#     qwen2.5-7b-instruct-q4_k_m.gguf --local-dir ./models

from llama_cpp import Llama
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DEFAULT_TRANSCRIPT_DIR = "/path/transcripts"
DEFAULT_OUT_DIR        = "/path/market_analysis"
DEFAULT_MODEL_PATH     = "./models/qwen2.5-7b-instruct-q4_k_m.gguf"

GPU_LAYERS         = 35       # Lower to 20-25 if CUDA out-of-memory
CONTEXT_SIZE       = 4096     # Context window (tokens)
MAX_RESPONSE_TOKENS = 800     # Max tokens per LLM response

# Pass 1: how many chars per transcript chunk
# ~3 chars/token, leaving room for prompt + response within CONTEXT_SIZE
PASS1_CHUNK_CHARS  = 2500

# Pass 2: how many chars per summary chunk (summaries are short, usually fits in one)
PASS2_CHUNK_CHARS  = 3000

# ── System Prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior financial analyst with deep expertise in global markets.
You extract market-relevant insights from financial transcripts.
Be crisp, specific, and factual. No filler. No repetition.
Always respond strictly in the format requested."""


# ── Pass 1 Prompt: per-chunk mini summary ─────────────────────────────────────
def pass1_prompt(chunk: str, chunk_num: int, total: int) -> str:
    return f"""[Chunk {chunk_num} of {total}]

Transcript excerpt:
\"\"\"
{chunk}
\"\"\"

Extract ONLY market-relevant information from this excerpt.
Respond in this EXACT format (skip any section if nothing relevant found):

KEY_POINTS:
- [point]: [its likely effect on markets, if any]

SECTORS_DOWN:
- [sector name]: [reason from this excerpt]

SECTORS_UP:
- [sector name]: [reason from this excerpt]

SENTIMENT_SIGNAL: [BULLISH / BEARISH / NEUTRAL / MIXED / UNCLEAR]
SENTIMENT_NOTE: [one line — what in this excerpt drives that signal]

If this excerpt has NO market-relevant content, respond only with:
NO_MARKET_CONTENT
"""


# ── Pass 2 Prompt: final analysis from compiled summaries ─────────────────────
def pass2_prompt_chunk(summary_chunk: str, chunk_num: int, total: int) -> str:
    """Used only if summaries are too large and need chunking in pass 2."""
    return f"""[Summary Part {chunk_num} of {total}]

Compiled mini-summaries from transcript analysis:
\"\"\"
{summary_chunk}
\"\"\"

From this section, extract:

UNIQUE_POINTS:
- [point]: [market effect]

SECTORS_DOWN:
- [sector]: [reason]

SECTORS_UP:
- [sector]: [reason]

SENTIMENT_SIGNALS: [list the signals seen — BULLISH / BEARISH / NEUTRAL]
"""


def pass2_final_prompt(compiled_summaries: str) -> str:
    """Used when all summaries fit in one pass — produces the final report directly."""
    return f"""Below are mini-summaries extracted from different parts of a financial transcript:

\"\"\"
{compiled_summaries}
\"\"\"

Now produce the FINAL market analysis report. Deduplicate — list each point ONCE only.
Respond in this EXACT format:

---
## 1. KEY POINTS & THEIR MARKET EFFECT (Global Perspective)
- [unique point]: [what it means for markets]
- [repeat for each unique point — most important first]

## 2. SECTORS LIKELY TO GO DOWN 📉
- [Sector Name]: [consolidated reason]
[Write "None identified" if empty]

## 3. SECTORS LIKELY TO GO UP 📈
- [Sector Name]: [consolidated reason]
[Write "None identified" if empty]

## 4. MARKET SENTIMENT ANALYSIS
Overall Sentiment: [BULLISH 🟢 / BEARISH 🔴 / NEUTRAL 🟡 / MIXED ⚪]
Confidence: [High / Medium / Low]
Reasoning: [2-4 lines — explain what in the transcript drives this classification,
            consider tone, language, the balance of risks vs opportunities mentioned]
---
"""


def pass2_consolidate_prompt(partial_extractions: list[str]) -> str:
    """If pass 2 needed chunking, consolidate those partial results here."""
    joined = "\n\n--- NEXT PART ---\n\n".join(partial_extractions)
    return f"""Below are partial analyses from different sections of compiled summaries:

{joined}

Consolidate into ONE final report. Remove duplicates. Most important points first.

---
## 1. KEY POINTS & THEIR MARKET EFFECT (Global Perspective)
- [unique point]: [market effect]

## 2. SECTORS LIKELY TO GO DOWN 📉
- [Sector Name]: [reason]
[Write "None identified" if empty]

## 3. SECTORS LIKELY TO GO UP 📈
- [Sector Name]: [reason]
[Write "None identified" if empty]

## 4. MARKET SENTIMENT ANALYSIS
Overall Sentiment: [BULLISH 🟢 / BEARISH 🔴 / NEUTRAL 🟡 / MIXED ⚪]
Confidence: [High / Medium / Low]
Reasoning: [2-4 lines]
---
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def run_llm(llm: Llama, user_prompt: str) -> str:
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": user_prompt}
        ],
        max_tokens=MAX_RESPONSE_TOKENS,
        temperature=0.15,
        repeat_penalty=1.1,
    )
    return response["choices"][0]["message"]["content"].strip()


def chunk_text(text: str, chunk_size: int) -> list[str]:
    """Split text into chunks at paragraph/sentence boundaries."""
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break
        split_at = text.rfind("\n\n", start, end)
        if split_at == -1:
            split_at = text.rfind(". ", start, end)
        if split_at == -1:
            split_at = end
        else:
            split_at += 1
        chunks.append(text[start:split_at])
        start = split_at
    return chunks


def extract_body(content: str) -> str:
    """Strip mp3_to_text.py header (Audio File / Language / dashes lines)."""
    lines = content.splitlines()
    body, header_done = [], False
    for line in lines:
        if not header_done and line.startswith("-" * 10):
            header_done = True
            continue
        if header_done:
            body.append(line)
    result = "\n".join(body).strip()
    return result if result else content.strip()


# ── Main Analysis Pipeline ────────────────────────────────────────────────────

def analyse_transcript(txt_path: Path, out_dir: Path, llm: Llama):
    out_dir.mkdir(parents=True, exist_ok=True)

    stem        = txt_path.stem
    summary_file = out_dir / f"{stem}_pass1_summaries.txt"   # intermediate
    final_file   = out_dir / f"{stem}_analysis.txt"          # final report

    # ── Read transcript ───────────────────────────────────────────────────────
    with open(txt_path, "r", encoding="utf-8") as f:
        raw = f.read()
    transcript = extract_body(raw)

    if not transcript:
        print(f"   Empty transcript, skipping.")
        return

    print(f"   Transcript: {len(transcript):,} chars")

    # ══════════════════════════════════════════════════════════════════════════
    # PASS 1 — MAP: chunk transcript → mini-summary per chunk
    # ══════════════════════════════════════════════════════════════════════════
    chunks = chunk_text(transcript, PASS1_CHUNK_CHARS)
    total  = len(chunks)
    print(f"\n   ── PASS 1: {total} chunk(s) → mini-summaries ──")

    mini_summaries = []
    for i, chunk in enumerate(chunks, 1):
        print(f"   Chunk {i}/{total}...", end=" ", flush=True)
        result = run_llm(llm, pass1_prompt(chunk, i, total))
        if result.strip() != "NO_MARKET_CONTENT":
            mini_summaries.append(f"[From chunk {i}/{total}]\n{result}")
            print("✓")
        else:
            print("(no market content, skipped)")

    if not mini_summaries:
        print("   No market-relevant content found in transcript.")
        return

    # Save intermediate summaries file
    compiled = "\n\n" + ("─" * 50) + "\n\n".join(mini_summaries)
    with open(summary_file, "w", encoding="utf-8") as f:
        f.write(f"Pass 1 Summaries — {txt_path.name}\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("=" * 60 + "\n")
        f.write(compiled)
    print(f"\n   Pass 1 done. Summaries saved → {summary_file.name}")

    # ══════════════════════════════════════════════════════════════════════════
    # PASS 2 — REDUCE: read compiled summaries → final report
    # ══════════════════════════════════════════════════════════════════════════
    print(f"\n   ── PASS 2: final analysis from summaries ──")
    print(f"   Compiled summaries: {len(compiled):,} chars")

    summary_chunks = chunk_text(compiled, PASS2_CHUNK_CHARS)

    if len(summary_chunks) == 1:
        # Summaries fit in one shot — best case
        print(f"   Single pass (summaries fit in context)...")
        final_analysis = run_llm(llm, pass2_final_prompt(compiled))

    else:
        # Summaries still too large — chunk and then consolidate
        print(f"   Summaries large — splitting into {len(summary_chunks)} parts...")
        partial_results = []
        for i, sc in enumerate(summary_chunks, 1):
            print(f"   Summary chunk {i}/{len(summary_chunks)}...", end=" ", flush=True)
            result = run_llm(llm, pass2_prompt_chunk(sc, i, len(summary_chunks)))
            partial_results.append(result)
            print("✓")
        print(f"   Consolidating...")
        final_analysis = run_llm(llm, pass2_consolidate_prompt(partial_results))

    # Save final report
    with open(final_file, "w", encoding="utf-8") as f:
        f.write(f"Source Transcript : {txt_path.name}\n")
        f.write(f"Model             : Qwen2.5-7B-Instruct Q4_K_M (local)\n")
        f.write(f"Generated         : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write("=" * 60 + "\n\n")
        f.write(final_analysis)
        f.write("\n")

    print(f"\n   ✅ Final report saved → {final_file.name}")


# ── Entry Point ───────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Local Market Analysis — Two-Pass Map-Reduce")
    print("=" * 60 + "\n")

    model_path     = input(f"Model path [{DEFAULT_MODEL_PATH}]: ").strip() or DEFAULT_MODEL_PATH
    transcript_dir = input(f"Transcript folder [{DEFAULT_TRANSCRIPT_DIR}]: ").strip() or DEFAULT_TRANSCRIPT_DIR
    out_dir        = input(f"Save output to [{DEFAULT_OUT_DIR}]: ").strip() or DEFAULT_OUT_DIR

    model_path     = Path(model_path)
    transcript_dir = Path(transcript_dir)
    out_dir        = Path(out_dir)

    if not model_path.exists():
        print(f"\nModel not found: {model_path}")
        print("Download it with:")
        print("  huggingface-cli download Qwen/Qwen2.5-7B-Instruct-GGUF \\")
        print("    qwen2.5-7b-instruct-q4_k_m.gguf --local-dir ./models")
        return

    if not transcript_dir.exists():
        print(f"\nTranscript folder not found: {transcript_dir}")
        return

    txt_files = sorted(transcript_dir.glob("*.txt"))
    if not txt_files:
        print(f"\nNo .txt files found in {transcript_dir}")
        return

    print(f"\nLoading model ({GPU_LAYERS} layers on GPU)... takes ~15 seconds")
    llm = Llama(
        model_path  = str(model_path),
        n_gpu_layers= GPU_LAYERS,
        n_ctx       = CONTEXT_SIZE,
        verbose     = False
    )
    print(f"Model ready! Processing {len(txt_files)} transcript(s).\n")

    for txt in txt_files:
        print(f"\n{'='*60}")
        print(f"→ {txt.name}")
        print(f"{'='*60}")
        try:
            analyse_transcript(txt, out_dir, llm)
        except Exception as e:
            print(f"   ERROR: {e}")

    print(f"\n{'='*60}")
    print("All done! Check your output folder.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()