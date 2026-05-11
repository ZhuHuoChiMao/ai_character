import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel




IM_START = "<|im_start|>"
IM_END = "<|im_end|>"


def encode_marker(tokenizer, text):
    return tokenizer.encode(text, add_special_tokens=False)


def encode_fields_start(tokenizer):
    return tokenizer.encode(IM_START + "fields\n", add_special_tokens=False)


def encode_question_block(tokenizer, question):
    text = IM_START + "question\n" + question.strip() + "\n" + IM_END + "\n"
    return tokenizer.encode(text, add_special_tokens=False)


def encode_answer_start(tokenizer):
    text = IM_START + "answer\n"
    return tokenizer.encode(text, add_special_tokens=False)


def encode_im_end(tokenizer):
    return tokenizer.encode(IM_END, add_special_tokens=False)


def tree_width_with_field_markers(tokenizer, node):
    fields_start_ids = encode_fields_start(tokenizer)
    im_end_ids = encode_im_end(tokenizer)

    content_width = tree_width(tokenizer, node)

    return len(fields_start_ids) + content_width + len(im_end_ids)



def encode_history(tokenizer, history):
    if len(history) == 0:
        return []

    text = ""

    for item in history:
        text += f"question:{item['question']}\n"
        text += f"answer:{item['answer']}\n"

    return tokenizer.encode(text, add_special_tokens=False)


def encode_question(tokenizer, question):
    text = f"question:{question}\nanswer:"
    return tokenizer.encode(text, add_special_tokens=False)



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

def encode_question_for_train_style(tokenizer, question):
    # 注意：你的训练代码目前是 tokenize_text(question)
    # 所以这里必须保持一致，不要加 question: 和 answer:
    return tokenize_text(tokenizer, question)


def build_infer_input_train_style(
    tokenizer,
    fields,
    question,
    generated_answer_ids,
):
    fields_start_ids = encode_fields_start(tokenizer)
    question_ids = encode_question_block(tokenizer, question)
    answer_start_ids = encode_answer_start(tokenizer)
    im_end_ids = encode_im_end(tokenizer)

    field_widths = [
        tree_width_with_field_markers(tokenizer, node)
        for node in fields
    ]

    field_max_width = max(field_widths) if field_widths else 0

    # 这里建议把 question 长度也纳入 max_width
    max_width = max(
        field_max_width,
        len(question_ids),
    )

    # 重点：
    # answer_start 也属于 answer 区域，所以 shift 要包含它
    shift = len(answer_start_ids) + len(generated_answer_ids)

    main_end = max_width - 1 + shift

    all_input_ids = []
    all_position_ids = []

    # 1. fields block:
    # <|im_start|>fields\n + field tree + <|im_end|>
    for node in fields:
        field_total_width = tree_width_with_field_markers(tokenizer, node)

        block_end = main_end
        block_start = block_end - field_total_width + 1

        fields_start_start = block_start
        fields_start_end = fields_start_start + len(fields_start_ids) - 1

        content_end = block_end - len(im_end_ids)
        content_right_end = content_end

        ids, pos = build_tree_positions(
            tokenizer=tokenizer,
            node=node,
            right_end=content_right_end,
        )

        im_end_start = block_end - len(im_end_ids) + 1
        im_end_end = block_end

        fields_start_pos = list(
            range(fields_start_start, fields_start_end + 1)
        )

        im_end_pos = list(
            range(im_end_start, im_end_end + 1)
        )

        all_input_ids.extend(fields_start_ids)
        all_position_ids.extend(fields_start_pos)

        all_input_ids.extend(ids)
        all_position_ids.extend(pos)

        all_input_ids.extend(im_end_ids)
        all_position_ids.extend(im_end_pos)

    # 2. question block:
    # <|im_start|>question\n + question + <|im_end|>
    question_end = max_width - 1 + shift
    question_start = question_end - len(question_ids) + 1

    question_pos = list(
        range(question_start, question_end + 1)
    )

    all_input_ids.extend(question_ids)
    all_position_ids.extend(question_pos)

    # 3. answer block:
    # <|im_start|>answer\n + generated_answer_ids
    # 注意：这里没有提前放 <|im_end|>
    answer_all_ids = answer_start_ids + generated_answer_ids

    answer_start_pos = max_width
    answer_pos = list(
        range(
            answer_start_pos,
            answer_start_pos + len(answer_all_ids)
        )
    )

    all_input_ids.extend(answer_all_ids)
    all_position_ids.extend(answer_pos)

    input_ids = torch.tensor([all_input_ids], dtype=torch.long)
    attention_mask = torch.ones_like(input_ids)
    position_ids = torch.tensor([all_position_ids], dtype=torch.long)

    return input_ids, attention_mask, position_ids

adapter_path = "./1"

base_model_name = "Qwen/Qwen3-4B-Instruct-2507"
adapter_path = "./1"

tokenizer = AutoTokenizer.from_pretrained(
    adapter_path,
    trust_remote_code=True,
)

if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

base_model = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    torch_dtype=torch.bfloat16,
    device_map="auto",
    trust_remote_code=True,
    attn_implementation="sdpa",
)

model = PeftModel.from_pretrained(
    base_model,
    adapter_path,
)

model.eval()
model.config.use_cache = False



def clean_answer(text):
    stop_words = [
        "\n用户：",
        "\nuser:",
        "\nquestion:",
        "\nfields:",
        "\n标签",
        "\n助手：",
        "\nanswer:",
        "fields:",
    ]

    for stop_word in stop_words:
        if stop_word in text:
            text = text.split(stop_word)[0]

    return text.strip()



@torch.no_grad()
def generate_with_tree_position_train_style(
    model,
    tokenizer,
    fields,
    question,
    max_new_tokens=2048,
    temperature=0.7,
    top_p=0.9,
    do_sample=True,
):
    generated_answer_ids = []

    device = next(model.parameters()).device

    im_end_ids = tokenizer.encode("<|im_end|>", add_special_tokens=False)
    im_end_token_id = im_end_ids[0] if len(im_end_ids) == 1 else None

    for step in range(max_new_tokens):
        input_ids, attention_mask, position_ids = build_infer_input_train_style(
            tokenizer=tokenizer,
            fields=fields,
            question=question,
            generated_answer_ids=generated_answer_ids,
        )

        input_ids = input_ids.to(device)
        attention_mask = attention_mask.to(device)
        position_ids = position_ids.to(device)

        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            position_ids=position_ids,
            use_cache=False,
        )

        logits = outputs.logits[:, -1, :]

        if do_sample:
            if temperature <= 0:
                next_token_id = torch.argmax(logits, dim=-1).item()
            else:
                logits = logits / temperature

                sorted_logits, sorted_indices = torch.sort(logits, descending=True)
                probs = torch.softmax(sorted_logits, dim=-1)
                cumulative_probs = probs.cumsum(dim=-1)

                sorted_indices_to_remove = cumulative_probs > top_p
                sorted_indices_to_remove[..., 1:] = sorted_indices_to_remove[..., :-1].clone()
                sorted_indices_to_remove[..., 0] = False

                sorted_logits[sorted_indices_to_remove] = -float("inf")

                probs = torch.softmax(sorted_logits, dim=-1)
                next_token_in_sorted = torch.multinomial(probs, num_samples=1)
                next_token_id = sorted_indices.gather(-1, next_token_in_sorted).item()
        else:
            next_token_id = torch.argmax(logits, dim=-1).item()

        if next_token_id == tokenizer.eos_token_id:
            break

        if im_end_token_id is not None and next_token_id == im_end_token_id:
            break

        generated_answer_ids.append(next_token_id)

        text = tokenizer.decode(
            generated_answer_ids,
            skip_special_tokens=True,
        )

        stop_words = [
            "\n用户：",
            "\n用户",
            "\nuser:",
            "\nuser",
            "\nquestion:",
            "\nquestion",
            "\nfields:",
            "\nfields",
            "\n标签",
            "\n助手：",
            "\nanswer:",
            "\nanswer",
            "<|im_end|>",
            "（结束）",
            "(结束)",
            "（全文）",
            "(全文)",
        ]

        for stop_word in stop_words:
            if stop_word in text:
                return text.split(stop_word)[0].strip()

        if text.endswith("\n\n"):
            return text.strip()

    return tokenizer.decode(
        generated_answer_ids,
        skip_special_tokens=True,
    ).strip()




fields = [
    [
        "我的身份是AI",
        "我的姓名是猫竹",
    ],
    [
        "我扮演的人的姓名是毛泽东",
        "出生日期是1893年12月26日",
        "出生地在湖南省湘潭市",
        "死亡日期是1976年9月9日",
        "父亲名毛贻昌，字顺生",
        "母亲是文七妹",
        "身份是伟大的马克思主义者，伟大的无产阶级革命家、战略家、理论家，中国共产党、中国人民解放军和中华人民共和国的主要缔造者和领导人",
    ],
    [
        "场景的当前具体时间是2026年5月5日13点20分",
        "中午",
        "场景地点位于家中",
        "我坐在凳子上，提笔准备写文章",
        [
            "我打算写1024字左右",
        ],
        "环境的感知是安静",
    ],
    [
        "我谈话的对象的身份是广大青年",
    ],
    [
        "观点是青年是社会中最富有朝气、最具有创造精神的力量。一个时代有一个时代的任务，一代青年有一代青年的责任。青年不能只关心个人安逸和眼前利益，而应当在学习、劳动、创造和服务人民中锻炼自己。逃避责任、贪图享乐、脱离人民的思想，是应当警惕和反对的。青年只有把个人奋斗同社会进步结合起来，才能真正实现自己的价值。",
        [
            "青年是否应该担当时代责任的视角六是青年奋斗关系国家未来。",
            "青年是否应该担当时代责任的视角五是反对贪图安逸和逃避责任。",
            "青年是否应该担当时代责任的视角四是学习和劳动是青年成长的道路。",
            "青年是否应该担当时代责任的视角三是个人理想应与人民利益结合。",
            "青年是否应该担当时代责任的视角二是时代责任不能回避。",
            "青年是否应该担当时代责任的视角一是青年是社会中最有生气的力量。",
        ],
        "主题是青年是否应该担当时代责任",
        "当前场景的目的是引导青年认识自身与国家、社会、人民之间的关系，强调青年应当把个人理想同民族前途、人民利益结合起来。",
    ],
]


question = "写一篇围绕主题的文章。"

answer = generate_with_tree_position_train_style(
    model=model,
    tokenizer=tokenizer,
    fields=fields,
    question=question,
    max_new_tokens=2048,
    temperature=0.7,
    top_p=0.9,
    do_sample=True,
)

print("助手：", answer)