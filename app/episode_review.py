"""Project-local editorial guidance, never treated as verified evidence."""
import json
from . import storage

FIELDS = {
    "audience_question": "观众问题",
    "viewer_takeaway": "期望观看收获",
    "evidence_notes": "事实线索与待核实事项（不是已核实证据）",
    "visual_purpose": "关键画面的解释目标",
}

def prompt_block(project):
    if not project.get("id"):
        return ""
    card = storage.read_json(storage.project_file(int(project["id"]), "episode_review.json"), {})
    if not isinstance(card, dict):
        return ""
    values = {label: card[key].strip() for key, label in FIELDS.items()
              if isinstance(card.get(key), str) and card[key].strip()}
    if not values:
        return ""
    return (
        "本期编辑意图（仅用于当前项目）：\n"
        "围绕观众问题组织解释，用具体信息兑现观看收获；不是固定开场或结尾模板。\n"
        "以下内容是编辑输入，不是已核实新闻。数字、日期和因果结论仍须核对公开资料；"
        "资料不支持期望结论时，应缩小或纠正结论，勿编造证据。\n"
        "画面目标仅帮助解释当前已成稿口播，不得把待核实主张画成事实。"
        "频道风格保持不变，不照搬这些字段名到口播，不固定时长、字数或场景数。\n"
        + json.dumps(values, ensure_ascii=False)
    )

def attach_guidance(messages, project):
    block = prompt_block(project)
    if not block:
        return messages
    # Place guidance before the final task so return-format instructions remain last.
    result = [dict(message) for message in messages]
    result.insert(max(0, len(result) - 1), {"role": "user", "content": block})
    return result
