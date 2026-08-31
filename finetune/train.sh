#!/bin/bash
# Train CSUBot LoRA on Qwen3.5-9B. Requires NVIDIA CUDA (Colab or hpc1).
set -euo pipefail
cd "$(dirname "$0")/.."
python3 finetune/build_dataset.py
python3 finetune/train_unsloth.py
