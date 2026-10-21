"""导出 OpenAPI JSON 规范

用法:
    python -m scripts.export_openapi

会生成:
    scripts/openapi.json — 接口规范(JSON)
"""
import json
import sys
import os

# 把项目根目录加到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openapi.json")

def main():
    spec = app.openapi()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(spec, f, ensure_ascii=False, indent=2)
    # 统计
    paths = spec.get("paths", {})
    print(f"✅ OpenAPI 已生成: {OUT}")
    print(f"   端点数: {sum(1 for p in paths.values() for m in p if m in ('get','post','put','delete','patch'))}")
    print(f"   路径数: {len(paths)}")
    print(f"   模型数: {len(spec.get('components', {}).get('schemas', {}))}")
    print()
    print("用法:")
    print("  1) 导入 Postman:File → Import → 选 openapi.json")
    print("  2) 给 JMeter 用:见 scripts/jmeter/README.md")
    print("  3) 浏览接口:打开 http://127.0.0.1:8000/docs 看 Swagger UI")


if __name__ == "__main__":
    main()
