# CSUBot local RAG benchmark (Mac, no HPC1)

This kit sends the **exact 100 questions** from the provided `askrowdy_results.csv` through a **local retrieval-augmented generation (RAG)** pipeline. It compares results to the existing AskRowdy answers, preserving question IDs, wording, and order.

## What it runs

- **Retriever:** local CSUB document text chunks embedded with **Ollama + `nomic-embed-text`**; embeddings are cached on your Mac.
- **Generator:** **Ollama + `qwen3:8b`** (or another installed local model).
- **Documents:** whatever independent official CSUB `.pdf`, `.txt`, `.md`, `.html`, `.htm`, or `.docx` files **you supply** in `docs/` (you can use `--docs /path/to/your/documents`).
- **Comparison:** `comparison_askrowdy_vs_rag.csv`, with the original AskRowdy answer, CSUBot RAG answer, retrieval sources, timing, and status.

**This is a standalone RAG implementation, not your exact HPC1 retriever.** Matching the original RAG implementation requires your actual CSUBot source code and its index/corpus, which were not present here.

## On your Mac

Unzip the package. Then open Terminal in the extracted `csubot_local_rag_kit` folder:

```bash
cd ~/Downloads/csubot_local_rag_kit
source ~/chatbot-env/bin/activate
python -m pip install -r requirements.txt
```

Have the Ollama Mac app installed and running (or start `ollama serve`). Download the models **once**:

```bash
ollama pull qwen3:8b
ollama pull nomic-embed-text
```

Copy your actual CSUB **source documents** into the `docs` folder. **Do not copy** `askrowdy_results.csv`, `questions_for_csubot.csv`, audit files, `train.jsonl`, or `valid.jsonl` into `docs`: this can leak answers, undermining the benchmark.

Try one question (the first run creates and caches the document embeddings):

```bash
python run_local_rag.py --ask "Where is the CSUB library?"
```

Run the first 3 questions and check the CSV:

```bash
python run_local_rag.py --limit 3
open comparison_askrowdy_vs_rag.csv
```

Then run **all 100**:

```bash
python run_local_rag.py
```

The script resumes successfully answered questions and reindexes/retests if the source documents or embedding model change. No CSUB HPC1 connection is used. Ollama API calls go to `127.0.0.1:11434` by default.

## If your docs are elsewhere

```bash
python run_local_rag.py --docs ~/SeniorProject2/knowledge --limit 3
```

The path above is **an example**. Use the folder that actually contains your independent CSUB source documents.

## Notes

- Internet is only required to download Ollama models (and to obtain CSUB documents if you haven't already). After that, document retrieval and inference are local.
- If an answer isn't covered by the supplied documents, the generator is instructed to say it cannot verify the answer. Coverage matters!
- If a PDF is image-only/scanned, OCR it first; this script does not OCR.
- Scores in `rag_best_similarity` are relative embedding cosine scores, **not** answer correctness scores. Grade accuracy against independently verified official CSUB facts.
- On low-memory Macs, change the generator with `OLLAMA_MODEL=qwen3:1.7b python run_local_rag.py --limit 3`; results won't be directly comparable to the original 8B run without labeling the different model.
