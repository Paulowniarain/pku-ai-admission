# pku-ai-admission

用于北大招生、元培、通班与智能学科咨询，也支持与清华无穹、新雅、姚班、计算机系及书院制的本科培养比较。

## 检索顺序

`scripts/search_sources.py` 会按下面的顺序返回结果：

1. `references/local-knowledge.json`：用户授权公开的补充资料，带文件哈希、页码/段落、时间、立场、可信度和使用限制；
2. `references/sources.json`：北大官方来源定位；
3. 回答动态问题时，再打开当前年度的北大或清华官方原页联网核验。

本地库中的宣传稿、个人分析、内部话术和匿名材料均不是官方证据，不能覆盖现行规则。

## 使用

```bash
python scripts/search_sources.py "无穹书院课程体系和通班有什么区别" --json
python scripts/search_sources.py "通班现在怎么招生" --scope tongban
```

## 校验

```bash
python scripts/verify_local_knowledge.py --as-of 2026-08-20
python scripts/verify_sources.py --as-of 2026-08-20
python scripts/eval_retrieval.py
```
