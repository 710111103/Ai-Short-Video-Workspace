"""Map gate repairs to actual defects; do not repeat failed work on unchanged input."""

def needs_sentence_split(result):
    return any(isinstance(item, dict) and item.get('where') == '口播句长'
               for item in result.get('issues', []))

def repeated_editorial_failure(result):
    if not result or not result.get('cache_hit') or result.get('passed'):
        return False
    actions = [str(item) for item in result.get('actions', [])]
    request_failed = bool(result.get('execution_failed')) or any(
        '自动修复失败' in item or 'timed out' in item.lower() for item in actions)
    if request_failed:
        import time
        retry_after = float(result.get('retry_after_epoch') or 0)
        return bool(retry_after and time.time() < retry_after)
    # Only a successfully returned editorial rewrite may be locked on unchanged input.
    return bool(result.get('reassessment_completed') and any('总编' in item and '失败' not in item for item in actions))


def compact_gate_result(result):
    """Remove recursive snapshots while retaining one compact prior assessment."""
    if not isinstance(result, dict):
        return result
    payload = {k: v for k, v in result.items() if k not in {'before', 'after', 'rounds', 'cache_hit', 'reused_at'}}
    assessment_keys = ('key','label','desc','score','passed','status','issues','details','checked_at','source_fingerprint')
    def assessment(value):
        return {k: value.get(k) for k in assessment_keys if k in value} if isinstance(value, dict) else {}
    before = assessment(result.get('before'))
    after = assessment(result.get('after'))
    if before: payload['before'] = before
    if after: payload['after'] = after
    rounds = result.get('rounds')
    if isinstance(rounds, list):
        payload['rounds'] = [{k:v for k,v in item.items() if k not in {'before','after','rounds'}} for item in rounds[-5:] if isinstance(item,dict)]
    return payload


def mark_execution_failure(result, error, fingerprint, checked_at):
    """Keep prior assessment explicitly historical; bind failed attempt to latest input."""
    import time
    result.update(status='failed', passed=False, execution_failed=True,
                  reassessment_completed=False, error=str(error),
                  source_fingerprint=fingerprint, checked_at=checked_at,
                  retry_after_epoch=time.time() + 60)
    result['actions'].append(f"自动修复失败：{error}")
    return result


def gate_round_message(result, index):
    if result.get('execution_failed') or result.get('retry_skipped'):
        return f"第 {index} 轮未完成复评：{result.get('error', '请求未完成')}（显示的分数为此前检查结果）"
    return f"第 {index} 轮复评 {int(result.get('score', 0) or 0)} 分，状态 {result.get('status')}"
