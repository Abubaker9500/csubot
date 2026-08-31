#!/usr/bin/env python3
"""
LoRA fine-tune Qwen/Qwen3.5-9B for CSUBot.

Qwen3.5 uses a hybrid Gated DeltaNet architecture. Train this on NVIDIA
(CUDA): Google Colab (T4/L4/A100) or hpc1. Standard mlx_lm.lora on a Mac
is not reliable for this model.

Usage (Linux GPU):
  pip install unsloth trl datasets
  python finetune/build_dataset.py
  python finetune/train_unsloth.py
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, 'finetune', 'data')
OUT_DIR = os.path.join(ROOT, 'finetune', 'lora_csubot')
GGUF_DIR = os.path.join(ROOT, 'finetune', 'gguf_csubot')

BASE_MODEL = os.environ.get('CSUBOT_BASE_MODEL', 'unsloth/Qwen3.5-9B')
MAX_SEQ = 2048
LORA_RANK = 16


def main():
    try:
        import torch
        if not torch.cuda.is_available():
            sys.exit(
                'No NVIDIA GPU detected. Qwen3.5-9B LoRA needs CUDA '
                '(Colab or HPC). This Mac cannot train that architecture reliably.'
            )
        from unsloth import FastModel
        from unsloth.chat_templates import get_chat_template
        from datasets import load_dataset
        from trl import SFTTrainer, SFTConfig
        from unsloth.chat_templates import train_on_responses_only
    except ImportError as e:
        sys.exit(f'Missing training packages: {e}\nInstall: pip install unsloth trl datasets')

    train_path = os.path.join(DATA_DIR, 'train.jsonl')
    valid_path = os.path.join(DATA_DIR, 'valid.jsonl')
    if not os.path.isfile(train_path):
        sys.exit('Run python finetune/build_dataset.py first.')

    model, tokenizer = FastModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=MAX_SEQ,
        load_in_4bit=True,
        full_finetuning=False,
    )
    try:
        tokenizer = get_chat_template(tokenizer, chat_template='qwen3.5')
    except Exception:
        tokenizer = get_chat_template(tokenizer, chat_template='qwen3')

    model = FastModel.get_peft_model(
        model,
        r=LORA_RANK,
        target_modules=[
            'q_proj', 'k_proj', 'v_proj', 'o_proj',
            'gate_proj', 'up_proj', 'down_proj',
        ],
        lora_alpha=LORA_RANK * 2,
        lora_dropout=0,
        bias='none',
        use_gradient_checkpointing='unsloth',
        random_state=42,
    )

    def to_text(ex):
        text = tokenizer.apply_chat_template(
            ex['messages'],
            tokenize=False,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        return {'text': text}

    raw = load_dataset('json', data_files={'train': train_path, 'valid': valid_path})
    train_ds = raw['train'].map(to_text)
    valid_ds = raw['valid'].map(to_text)

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        train_dataset=train_ds,
        eval_dataset=valid_ds,
        args=SFTConfig(
            output_dir=OUT_DIR,
            per_device_train_batch_size=1,
            gradient_accumulation_steps=8,
            warmup_steps=10,
            num_train_epochs=3,
            learning_rate=2e-4,
            logging_steps=5,
            eval_strategy='steps',
            eval_steps=20,
            save_steps=50,
            max_seq_length=MAX_SEQ,
            dataset_text_field='text',
            report_to='none',
            seed=42,
        ),
    )
    trainer = train_on_responses_only(
        trainer,
        instruction_part='<|im_start|>user\n',
        response_part='<|im_start|>assistant\n',
    )
    trainer.train()
    model.save_pretrained(OUT_DIR)
    tokenizer.save_pretrained(OUT_DIR)
    print(f'Saved LoRA adapter to {OUT_DIR}')

    try:
        model.save_pretrained_gguf(GGUF_DIR, tokenizer, quantization_method='q4_k_m')
        print(f'Saved GGUF to {GGUF_DIR}')
        print('Then: ollama create csubot -f finetune/Modelfile')
    except Exception as e:
        print(f'GGUF export failed ({e}). Adapter is still saved; convert on HPC later.')


if __name__ == '__main__':
    main()
