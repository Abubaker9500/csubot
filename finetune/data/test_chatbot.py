
import csv
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

WEBSITE = "https://www.csub.edu/"
INPUT_FILE = "questions.csv"
OUTPUT_FILE = "askrowdy_results.csv"


def clean_answer(text):
    # Remove chatbot label
    text = re.sub(
        r"^\s*AskRowdy said:\s*",
        "",
        text,
        flags=re.IGNORECASE
    )

    # Remove feedback question
    text = re.sub(
        r"\s*Did this answer your question\?\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    return text.strip()


def ask_question(browser, question):
    # Fresh context prevents previous questions
    # from influencing the next response.
    context = browser.new_context()
    page = context.new_page()

    try:
        page.goto(
            WEBSITE,
            wait_until="domcontentloaded",
            timeout=45000
        )

        # Open AskRowdy
        page.get_by_test_id(
            "bubble-button"
        ).click(timeout=20000)

        close_button = page.get_by_label(
            "Close", exact=True
        )

        if (
            close_button.count() > 0
            and close_button.is_visible()
        ):
            close_button.click()

        # Find chatbot textbox
        textbox = page.get_by_role(
            "textbox",
            name="Ask a question"
        )

        textbox.wait_for(
            state="visible",
            timeout=15000
        )

        # Send question
        textbox.fill(question)

        start = time.perf_counter()
        textbox.press("Enter")

        # Wait for AskRowdy to finish
        feedback = page.get_by_text(
            "Did this answer your question?",
            exact=False
        ).last

        feedback.wait_for(
            state="visible",
            timeout=90000
        )

        response_time = round(
            time.perf_counter() - start, 2
        )

        # Extract the Level 3 response
        response_container = feedback.locator(
            "xpath=../../.."
        )

        raw_answer = response_container.inner_text()
        answer = clean_answer(raw_answer)

        if not answer:
            raise ValueError("Empty chatbot answer")

        # Capture any links in the answer
        links = response_container.locator(
            "a"
        ).evaluate_all(
            "(elements) => elements.map(a => a.href)"
        )

        return (
            answer,
            response_time,
            " | ".join(dict.fromkeys(links))
        )

    finally:
        context.close()


def main():
    # Load all questions
    with open(
        INPUT_FILE,
        newline="",
        encoding="utf-8-sig"
    ) as file:
        reader = csv.DictReader(file)

        if not reader.fieldnames or "question" not in reader.fieldnames:
            raise ValueError(
                "questions.csv needs a 'question' column"
            )

        questions = list(reader)

    # Remember successfully completed questions
    completed = set()

    if Path(OUTPUT_FILE).exists():
        with open(
            OUTPUT_FILE,
            newline="",
            encoding="utf-8"
        ) as file:
            for row in csv.DictReader(file):
                if row.get("status") == "success":
                    completed.add(row["id"])

    file_exists = (
        Path(OUTPUT_FILE).exists()
        and Path(OUTPUT_FILE).stat().st_size > 0
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=False
        )

        with open(
            OUTPUT_FILE,
            "a",
            newline="",
            encoding="utf-8"
        ) as output:

            writer = csv.writer(output)

            if not file_exists:
                writer.writerow([
                    "id",
                    "question",
                    "answer",
                    "response_time_seconds",
                    "sources",
                    "status"
                ])

            for index, item in enumerate(questions, 1):
                question_id = item.get("id") or str(index)
                question = item["question"].strip()

                if not question or question_id in completed:
                    continue

                print(f"\n[{index}/{len(questions)}]")
                print("QUESTION:", question)

                answer = ""
                response_time = ""
                sources = ""
                status = "error"

                # Retry once if the request fails
                for attempt in range(2):
                    try:
                        answer, response_time, sources = (
                            ask_question(browser, question)
                        )

                        status = "success"
                        break

                    except Exception as error:
                        status = f"error: {error}"
                        print(
                            f"Attempt {attempt + 1} failed:",
                            error
                        )
                        time.sleep(3)

                print("ANSWER:", answer or status)
                print("TIME:", response_time)

                writer.writerow([
                    question_id,
                    question,
                    answer,
                    response_time,
                    sources,
                    status
                ])

                # Save immediately to avoid losing results
                output.flush()

                # Small delay between questions
                time.sleep(3)

        browser.close()

    print("\nBENCHMARK COMPLETED!")
    print("Results saved to:", OUTPUT_FILE)


if __name__ == "__main__":
    main()

