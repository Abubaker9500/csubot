"""
Ask every question in questions.csv through the same RAG prompt CSUBot uses,
against a local Ollama. Saves the answer and which knowledge chunks were used.

This does not go through Flask or the website. It imports rag.py directly.

Usage (from anywhere):
    python finetune/data/ask_rag.py
    python finetune/data/ask_rag.py --model qwen3:1.7b --limit 5

Re-running skips questions that already succeeded, so you can stop and resume.
"""

import argparse
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

import rag  # noqa: E402

INPUT_FILE = HERE / "questions.csv"
OUTPUT_FILE = HERE / "csubot_rag_results.csv"
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")


def ask(question, model, timeout):
    chunks = rag.retrieve(question)
    sources = " | ".join(f'{c["source"]} — {c["title"]}' for c in chunks)
    messages = [
        {"role": "system", "content": rag.build_system_prompt(question)},
        {"role": "user", "content": question},
    ]
    start = time.perf_counter()
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": "2h",
        "options": {"temperature": 0.2},
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Ollama HTTP {e.code}: {detail}") from e
    answer = (body.get("message") or {}).get("content", "").strip()
    if not answer:
        raise ValueError("Empty model answer")
    return answer, sources, round(time.perf_counter() - start, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.environ.get("CSUBOT_MODEL", "qwen3:1.7b"))
    ap.add_argument("--input", type=Path, default=INPUT_FILE)
    ap.add_argument("--output", type=Path, default=OUTPUT_FILE)
    ap.add_argument("--timeout", type=int, default=180, help="seconds to wait per answer")
    ap.add_argument("--limit", type=int, default=0, help="stop after this many new questions (0 = all)")
    args = ap.parse_args()

    try:
        with urllib.request.urlopen(f"{OLLAMA_HOST}/api/tags", timeout=10) as r:
            tags = json.loads(r.read().decode())
    except urllib.error.URLError as e:
        raise SystemExit(f"Could not reach Ollama at {OLLAMA_HOST}: {e}") from e
    installed = {m["name"] for m in tags.get("models", [])}
    if args.model not in installed and f"{args.model}:latest" not in installed:
        names = ", ".join(sorted(installed)) or "(none)"
        raise SystemExit(f"Model {args.model!r} is not installed. Local models: {names}")

    with open(args.input, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "question" not in reader.fieldnames:
            raise SystemExit(f"{args.input} needs a 'question' column")
        questions = list(reader)

    completed = set()
    if args.output.exists():
        with open(args.output, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") == "success":
                    completed.add(row["id"])

    file_exists = args.output.exists() and args.output.stat().st_size > 0
    print(f"Ollama {OLLAMA_HOST}  model {args.model}  {len(questions)} questions")

    asked = 0
    with open(args.output, "a", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        if not file_exists:
            writer.writerow([
                "id", "question", "category", "sources", "answer",
                "response_time_seconds", "model", "status",
            ])

        for index, item in enumerate(questions, 1):
            qid = item.get("id") or str(index)
            question = (item.get("question") or "").strip()
            if not question or qid in completed:
                continue
            if args.limit and asked >= args.limit:
                break

            print(f"\n[{index}/{len(questions)}] {question}")
            answer, sources, elapsed, status = "", "", "", "error"
            try:
                answer, sources, elapsed = ask(question, args.model, args.timeout)
                status = "success"
            except Exception as e:
                status = f"error: {e}"
                print(f"  FAILED: {e}")

            preview = (answer or status).replace("\n", " ")
            print(f"  SOURCES: {sources or '(none)'}")
            print(f"  ANSWER: {preview[:400]}")
            print(f"  TIME: {elapsed}s")

            writer.writerow([
                qid, question, item.get("category", ""), sources, answer,
                elapsed, args.model, status,
            ])
            output.flush()
            asked += 1

    print(f"\nDONE. {asked} new answers written to {args.output}")


if __name__ == "__main__":
    main()
