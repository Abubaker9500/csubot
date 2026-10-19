import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import requests

INPUT_FILE = "questions.csv"
OUTPUT_FILE = "csubot_results.csv"


def login(session, base_url, email, password):
    r = session.post(
        f"{base_url}/login",
        data={"email": email, "password": password},
        allow_redirects=False,
        timeout=30,
    )
    location = r.headers.get("Location", "")
    if r.status_code not in (301, 302, 303) or "/login" in location:
        raise SystemExit(f"Login failed for {email} (HTTP {r.status_code}, Location={location!r})")

    health = session.get(f"{base_url}/health", timeout=30).json()
    return health.get("model", "?")


def ask_question(session, base_url, question, timeout):
    start = time.perf_counter()
    first_token = None
    parts = []
    error = None

    with session.post(
        f"{base_url}/chat",
        json={"messages": [{"role": "user", "content": question}]},
        stream=True,
        timeout=(30, timeout),
    ) as r:
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

        for line in r.iter_lines():
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "error" in obj:
                error = obj["error"]
                break
            content = obj.get("message", {}).get("content", "")
            if content:
                if first_token is None:
                    first_token = time.perf_counter() - start
                parts.append(content)
            if obj.get("done"):
                break

    if error:
        raise RuntimeError(error)

    answer = "".join(parts).strip()
    if not answer:
        raise ValueError("Empty chatbot answer")

    total = time.perf_counter() - start
    return answer, round(total, 2), round(first_token or total, 2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=os.environ.get("CSUBOT_URL", "http://127.0.0.1:5001"))
    ap.add_argument("--email", default=os.environ.get("CSUBOT_EMAIL", "test@csub.edu"))
    ap.add_argument("--password", default=os.environ.get("CSUBOT_PASSWORD"))
    ap.add_argument("--input", default=INPUT_FILE)
    ap.add_argument("--output", default=OUTPUT_FILE)
    ap.add_argument("--timeout", type=int, default=300, help="seconds to wait per answer")
    ap.add_argument("--delay", type=float, default=0, help="seconds to sleep between questions")
    args = ap.parse_args()

    if not args.password:
        ap.error("--password is required (or set CSUBOT_PASSWORD)")

    base_url = args.url.rstrip("/")

    with open(args.input, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "question" not in reader.fieldnames:
            raise SystemExit("questions.csv needs a 'question' column")
        questions = list(reader)

    completed = set()
    if Path(args.output).exists():
        with open(args.output, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("status") == "success":
                    completed.add(row["id"])

    file_exists = Path(args.output).exists() and Path(args.output).stat().st_size > 0

    session = requests.Session()
    model = login(session, base_url, args.email, args.password)
    print(f"Logged in to {base_url} as {args.email} (model: {model})")

    with open(args.output, "a", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        if not file_exists:
            writer.writerow([
                "id", "question", "category", "answer",
                "response_time_seconds", "first_token_seconds", "model", "status",
            ])

        for index, item in enumerate(questions, 1):
            qid = item.get("id") or str(index)
            question = item["question"].strip()
            if not question or qid in completed:
                continue

            print(f"\n[{index}/{len(questions)}] {question}")

            answer, total, first = "", "", ""
            status = "error"
            for attempt in range(2):
                try:
                    answer, total, first = ask_question(session, base_url, question, args.timeout)
                    status = "success"
                    break
                except Exception as e:
                    status = f"error: {e}"
                    print(f"  attempt {attempt + 1} failed: {e}")
                    time.sleep(3)

            print(f"  ANSWER: {(answer or status)[:300]}")
            print(f"  TIME: {total}s (first token {first}s)")

            writer.writerow([
                qid, question, item.get("category", ""), answer,
                total, first, model, status,
            ])
            output.flush()

            if args.delay:
                time.sleep(args.delay)

    print("\nDONE. Results saved to:", args.output)


if __name__ == "__main__":
    main()
