"""Consume chat streams with separate inactivity and total request limits."""
import time
from types import SimpleNamespace

def request_editor_stream(client, *, total_timeout=600, progress=None, **kwargs):
    started=time.monotonic()
    content=[]; reasoning=[]; finish=None; usage=None; first=None
    last_progress = -10.0
    stream=client.chat.completions.create(stream=True, **kwargs)
    try:
        for chunk in stream:
            elapsed=time.monotonic()-started
            if elapsed > total_timeout:
                raise TimeoutError(f'总编生成超过总时限 {total_timeout} 秒，原稿保留')
            if getattr(chunk,'usage',None):usage=chunk.usage
            for choice in chunk.choices or []:
                if getattr(choice,'index',0)!=0:continue
                delta=choice.delta
                text=getattr(delta,'content',None)
                thought=getattr(delta,'reasoning_content',None)
                if (text or thought) and first is None:first=elapsed
                if text:content.append(text)
                if thought:reasoning.append(thought)
                if choice.finish_reason:finish=choice.finish_reason
            if progress and elapsed - last_progress >= 10:
                progress({'status':'streaming','elapsed_seconds':round(elapsed, 1),
                          'first_token_seconds':first,'content_length':sum(map(len,content)),
                          'reasoning_length':sum(map(len,reasoning))})
                last_progress=elapsed
    finally:
        stream.close()
    if not finish:
        raise RuntimeError('总编响应流提前断开，未收到完成标记；原稿保留')
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=''.join(content),reasoning_content=''.join(reasoning)),finish_reason=finish)],usage=usage,
                           timing={'first_token_seconds':first,'elapsed_seconds':time.monotonic()-started})
