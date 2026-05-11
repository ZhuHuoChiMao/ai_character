import json
import inspect
import torch
from torch.utils.data import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    Trainer,
    TrainingArguments,
)
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training


# =========================
# 你的 position 构造函数
# =========================

def tokenize_text(tokenizer, text):
    text = text.strip() + "\n"
    return tokenizer.encode(text, add_special_tokens=False)


def split_node(node):
    parent_texts = []
    child_nodes = []

    for item in node:
        if isinstance(item, str):
            parent_texts.append(item)
        elif isinstance(item, list):
            child_nodes.append(item)
        else:
            raise TypeError(f"不支持的类型: {type(item)}")

    return parent_texts, child_nodes


def encode_parent(tokenizer, parent_texts):
    if len(parent_texts) == 0:
        return []

    parent_text = "，".join(parent_texts)
    return tokenize_text(tokenizer, parent_text)


def tree_width(tokenizer, node):
    parent_texts, child_nodes = split_node(node)
    parent_ids = encode_parent(tokenizer, parent_texts)
    parent_len = len(parent_ids)

    child_widths = [tree_width(tokenizer, child) for child in child_nodes]
    max_child_width = max(child_widths) if child_widths else 0

    return max_child_width + parent_len


def build_tree_positions(tokenizer, node, right_end):
    all_ids = []
    all_pos = []

    parent_texts, child_nodes = split_node(node)
    parent_ids = encode_parent(tokenizer, parent_texts)
    parent_len = len(parent_ids)

    if parent_len > 0:
        parent_start = right_end - parent_len + 1
        parent_end = right_end
    else:
        parent_start = right_end + 1
        parent_end = right_end

    child_end = parent_start - 1

    for child in child_nodes:
        child_ids, child_pos = build_tree_positions(
            tokenizer=tokenizer,
            node=child,
            right_end=child_end,
        )

        all_ids.extend(child_ids)
        all_pos.extend(child_pos)

    if parent_len > 0:
        parent_pos = list(range(parent_start, parent_end + 1))
        all_ids.extend(parent_ids)
        all_pos.extend(parent_pos)

    return all_ids, all_pos





def build_train_items_from_tree_list_prefix(
    tokenizer,
    fields,
    question,
    answer,
    max_length=2048,
    min_answer_tokens=1,
):
    widths = [tree_width(tokenizer, node) for node in fields]
    max_width = max(widths)

    items = []

    question_ids = tokenize_text(tokenizer, question)
    answer_ids = tokenize_text(tokenizer, answer)

    # 先算完整 fields token 数
    fields_ids_all = []
    fields_pos_all = []

    for node in fields:
        ids, pos = build_tree_positions(
            tokenizer=tokenizer,
            node=node,
            right_end=max_width - 1,
        )
        fields_ids_all.extend(ids)
        fields_pos_all.extend(pos)

    base_len = len(fields_ids_all) + len(question_ids)

    max_answer_tokens = max_length - base_len

    if max_answer_tokens < min_answer_tokens:
        max_answer_tokens = min_answer_tokens

    answer_ids = answer_ids[-max_answer_tokens:]

    for step in range(1, len(answer_ids) + 1):
        current_answer_ids = answer_ids[:step]

        shift = step - 1

        main_end = max_width - 1 + shift

        all_input_ids = []
        all_position_ids = []

        # fields
        for node in fields:
            ids, pos = build_tree_positions(
                tokenizer=tokenizer,
                node=node,
                right_end=main_end,
            )

            all_input_ids.extend(ids)
            all_position_ids.extend(pos)

        # question
        question_end = max_width - 1 + shift
        question_start = question_end - len(question_ids) + 1

        question_pos = list(range(question_start, question_end + 1))

        all_input_ids.extend(question_ids)
        all_position_ids.extend(question_pos)

        # answer
        answer_start = max_width
        answer_pos = list(
            range(
                answer_start,
                answer_start + len(current_answer_ids)
            )
        )

        all_input_ids.extend(current_answer_ids)
        all_position_ids.extend(answer_pos)

        labels = [-100] * len(all_input_ids)
        labels[-1] = current_answer_ids[-1]

        items.append({
            "input_ids": all_input_ids,
            "attention_mask": [1] * len(all_input_ids),
            "position_ids": all_position_ids,
            "labels": labels,
        })

    return items

# =========================
# Dataset
# =========================

import os
import glob
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAIN_PATH = ROOT / "datasets" / "train.jsonl"
OUTPUT_DIR = ROOT / "models" / "lora"


def env_int(name, default):
    return int(os.environ.get(name, str(default)))


def env_float(name, default):
    return float(os.environ.get(name, str(default)))


def env_bool(name, default):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default):
    value = os.environ.get(name)
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


def make_training_args(**kwargs):
    supported = inspect.signature(TrainingArguments.__init__).parameters
    return TrainingArguments(**{key: value for key, value in kwargs.items() if key in supported})


def resolve_torch_dtype():
    value = os.environ.get("TORCH_DTYPE", "bfloat16").strip().lower()
    if value in {"auto", ""}:
        return "auto"
    if value in {"float32", "fp32"}:
        return torch.float32
    if value in {"float16", "fp16"}:
        return torch.float16
    if value in {"bfloat16", "bf16"}:
        return torch.bfloat16
    raise ValueError("TORCH_DTYPE 只支持 auto、float32、float16、bfloat16")


def resolve_bnb_compute_dtype():
    value = os.environ.get("BNB_COMPUTE_DTYPE", "").strip().lower()
    if not value:
        if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
            return torch.bfloat16
        return torch.float16
    if value in {"float16", "fp16"}:
        return torch.float16
    if value in {"bfloat16", "bf16"}:
        return torch.bfloat16
    if value in {"float32", "fp32"}:
        return torch.float32
    raise ValueError("BNB_COMPUTE_DTYPE 只支持 float16、bfloat16、float32")


def resolve_quantization_config():
    default_quantization = "none"
    value = os.environ.get("BNB_QUANTIZATION", default_quantization).strip().lower()
    if value in {"", "none", "off", "false", "0"}:
        return None
    if not torch.cuda.is_available():
        raise RuntimeError("bitsandbytes 量化训练需要 NVIDIA CUDA。CPU 训练请设置 BNB_QUANTIZATION=none")
    if value in {"4bit", "4-bit", "qlora"}:
        return BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=resolve_bnb_compute_dtype(),
            bnb_4bit_quant_type=os.environ.get("BNB_4BIT_QUANT_TYPE", "nf4"),
            bnb_4bit_use_double_quant=env_bool("BNB_4BIT_USE_DOUBLE_QUANT", True),
        )
    if value in {"8bit", "8-bit"}:
        return BitsAndBytesConfig(load_in_8bit=True)
    raise ValueError("BNB_QUANTIZATION 只支持 none、4bit、8bit")

class TreePositionDataset(Dataset):
    def __init__(self, path, tokenizer, max_length=2048):
        self.data = []
        self.tokenizer = tokenizer
        self.max_length = max_length

        # 如果 path 是文件夹，就读取里面所有 .jsonl 文件
        if os.path.isdir(path):
            file_paths = sorted(glob.glob(os.path.join(path, "*.jsonl")))
        else:
            file_paths = [path]

        for file_path in file_paths:
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    example = json.loads(line)

                    items = build_train_items_from_tree_list_prefix(
                        tokenizer=tokenizer,
                        fields=example["fields"],
                        question=example["prompt_q"],
                        answer=example["prompt_a"],
                        max_length=max_length,
                    )

                    for item in items:
                        if len(item["input_ids"]) > max_length:
                            item = self.left_truncate(item, max_length)

                        item["length"] = len(item["input_ids"])
                        self.data.append(item)

    def left_truncate(self, item, max_length):
        for key in ["input_ids", "attention_mask", "position_ids", "labels"]:
            item[key] = item[key][-max_length:]

        return item

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        return self.data[idx]


# =========================
# Collator：负责 padding
# =========================

class TreePositionCollator:
    def __init__(self, tokenizer):
        self.tokenizer = tokenizer
        self.pad_token_id = tokenizer.pad_token_id

    def __call__(self, features):
        max_len = max(len(x["input_ids"]) for x in features)

        batch_input_ids = []
        batch_attention_mask = []
        batch_position_ids = []
        batch_labels = []

        for x in features:
            length = len(x["input_ids"])
            pad_len = max_len - length

            batch_input_ids.append(
                x["input_ids"] + [self.pad_token_id] * pad_len
            )

            batch_attention_mask.append(
                x["attention_mask"] + [0] * pad_len
            )

            # padding 部分 position_ids 填 0 即可，因为 attention_mask=0
            batch_position_ids.append(
                x["position_ids"] + [0] * pad_len
            )

            batch_labels.append(
                x["labels"] + [-100] * pad_len
            )

        return {
            "input_ids": torch.tensor(batch_input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(batch_attention_mask, dtype=torch.long),
            "position_ids": torch.tensor(batch_position_ids, dtype=torch.long),
            "labels": torch.tensor(batch_labels, dtype=torch.long),
        }


# =========================
# 训练主函数
# =========================

def main():
    # model_name = "Qwen/Qwen3-4B-Instruct-2507"
    model_name = os.environ.get("BASE_MODEL", "Qwen/Qwen3-4B-Instruct-2507")

    # train_path = "traindatasets"
    train_path = os.environ.get("TRAIN_PATH", str(TRAIN_PATH))

    # output_dir = "./qwen3_4b_lora_tree_position"
    output_dir = os.environ.get("OUTPUT_DIR", str(OUTPUT_DIR))

    tokenizer = AutoTokenizer.from_pretrained(
        model_name,
        trust_remote_code=True,
    )

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    quantization_config = resolve_quantization_config()
    use_kbit_training = quantization_config is not None

    model_kwargs = {
        "trust_remote_code": True,
    }
    if not use_kbit_training:
        model_kwargs["torch_dtype"] = resolve_torch_dtype()
    else:
        model_kwargs["quantization_config"] = quantization_config
    device_map = os.environ.get("DEVICE_MAP", "auto").strip()
    if device_map:
        model_kwargs["device_map"] = device_map
    attn_implementation = os.environ.get("ATTN_IMPLEMENTATION", "sdpa").strip()
    if attn_implementation:
        model_kwargs["attn_implementation"] = attn_implementation

    model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)

    model.config.use_cache = False
    if use_kbit_training:
        model = prepare_model_for_kbit_training(
            model,
            use_gradient_checkpointing=env_bool("GRADIENT_CHECKPOINTING", True),
        )


    lora_config = LoraConfig(
        r=env_int("LORA_R", 16),
        lora_alpha=env_int("LORA_ALPHA", 32),
        lora_dropout=env_float("LORA_DROPOUT", 0.05),
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=env_list("LORA_TARGET_MODULES", [
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ]),
    )

    model = get_peft_model(model, lora_config)

    model.print_trainable_parameters()

    train_dataset = TreePositionDataset(
        path=train_path,
        tokenizer=tokenizer,
        max_length=env_int("MAX_LENGTH", 2500),
    )

    collator = TreePositionCollator(tokenizer)

    training_args = make_training_args(
        output_dir=output_dir,

        per_device_train_batch_size=env_int("BATCH_SIZE", 3),
        gradient_accumulation_steps=env_int("GRADIENT_ACCUMULATION_STEPS", 4),

        num_train_epochs=env_float("NUM_TRAIN_EPOCHS", 3),
        learning_rate=env_float("LEARNING_RATE", 1e-4),

        logging_steps=env_int("LOGGING_STEPS", 200),
        save_steps=env_int("SAVE_STEPS", 5000),
        save_total_limit=env_int("SAVE_TOTAL_LIMIT", 2),

        bf16=env_bool("BF16", torch.cuda.is_available() and torch.cuda.is_bf16_supported()),
        fp16=env_bool("FP16", torch.cuda.is_available() and not torch.cuda.is_bf16_supported()),

        optim=os.environ.get(
            "OPTIM",
            "paged_adamw_8bit" if use_kbit_training else ("adamw_torch_fused" if torch.cuda.is_available() else "adamw_torch"),
        ),

        lr_scheduler_type="cosine",
        warmup_ratio=env_float("WARMUP_RATIO", 0.03),

        report_to="none",

        remove_unused_columns=False,

        dataloader_num_workers=env_int("DATALOADER_NUM_WORKERS", 8),
        dataloader_pin_memory=env_bool("DATALOADER_PIN_MEMORY", True),

        group_by_length=True,
        length_column_name="length",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=collator,
    )

    # trainer.train()
    # trainer.train(resume_from_checkpoint="./qwen3_4b_lora_tree_position/checkpoint-10001")
    resume_checkpoint = os.environ.get("RESUME_CHECKPOINT")
    if resume_checkpoint:
        trainer.train(resume_from_checkpoint=resume_checkpoint)
    else:
        trainer.train()

    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)

    print(f"saved to {output_dir}")


if __name__ == "__main__":
    main()
