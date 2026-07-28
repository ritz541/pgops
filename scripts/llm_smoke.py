import os
from dotenv import load_dotenv; load_dotenv(".env")
import litellm
try:
    r = litellm.completion(model=os.getenv("LLM_MODEL"), api_key=os.getenv("AGNES_API_KEY"),
        base_url=os.getenv("LLM_BASE_URL"), messages=[{"role":"user","content":"reply with just: ok"}], max_tokens=10)
    print("PRIMARY OK:", r.choices[0].message.content)
except Exception as e:
    print("PRIMARY FAIL:", repr(e)[:300])
try:
    r = litellm.completion(model="openrouter/qwen/qwen3.7-flash",
        api_key=os.getenv("OPENROUTER_API_KEY"),
        messages=[{"role":"user","content":"reply with just: ok"}], max_tokens=10)
    print("FALLBACK OK:", r.choices[0].message.content)
except Exception as e:
    print("FALLBACK FAIL:", repr(e)[:300])
