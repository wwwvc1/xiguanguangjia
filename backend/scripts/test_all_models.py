import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.llm_factory import test_model_connection
for mid in (1, 12, 13):
    r = test_model_connection(mid, "只回复两个字:可用")
    print(f"id={mid:<3} success={str(r['success']):<6} {r['latency_ms']:>6}ms  "
          f"{(r['reply'] or r['error'] or '')[:70]}")
