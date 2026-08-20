# 协作开发约定

本仓库的 `main` 分支保存可验证、可安装的 Skill。每项工作从最新 `main` 创建独立分支，通过 Pull Request 合并。

## 文件所有权

| 角色 | 独占维护文件 |
|---|---|
| 对话能力负责人 | `SKILL.md`、`references/conversation-guide.md`、`references/dialogue-rubric.md` |
| 通班知识库负责人 | `references/sources.json`、`references/domain-guide.md`、`references/eval-cases.json`；确有需要时修改 `scripts/source_lib.py` |
| 学长 | `references/dialogues/senior-examples.md` |
| 学弟 | `references/dialogues/junior-examples.md` |

除最终集成人外，不在同一 Pull Request 中顺手修改其他负责人的文件。若一项需求确实跨越边界，先在 Pull Request 描述中说明，再由对应负责人完成其文件内的改动。

## 分支建议

- `feature/conversation-guidance`
- `feature/tongban-knowledge`
- `examples/senior-dialogues`
- `examples/junior-dialogues`

学长和学弟应在前两条功能分支合入后，从最新 `main` 创建示范分支。最后由对话能力负责人把通过评审的示范链接加入对话指南或 Skill 入口。

## 提交前验证

在仓库根目录运行：

```powershell
python scripts/verify_sources.py --as-of YYYY-MM-DD
python scripts/eval_retrieval.py
```

修改检索逻辑、来源数据或评测用例时，两项都必须通过。修改对话指南或示范时，还需依据 `references/dialogue-rubric.md` 进行人工复核。

不要提交访问令牌、个人联系方式、未公开招生材料、下载缓存、虚拟环境或 `__pycache__`。
