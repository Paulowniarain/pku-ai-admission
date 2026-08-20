---
name: pku-ai-admissions
description: 检索、核验并回答北京大学招生咨询，覆盖北大本科与研究生招生、元培学院、通用人工智能实验班（通班），以及智能科学与技术专业、智班、智能学院、人工智能研究院的本科、硕士、博士和夏令营；也支持与清华无穹书院、新雅书院、姚班、计算机系及相关书院的本科培养比较。用户询问招生入口、项目区别、培养模式、报名条件、名额、截止时间、专业目录、导师、费用、校区、联系方式、北清项目比较或要求核对相关说法时使用。
---

# 北京大学招生咨询与智能学科核验

## 执行工作流

1. 先判断用户真正需要的是事实核验、项目比较、个人路径分析、行动建议，还是对外咨询话术。只有缺失信息会实质改变结论或下一步时才追问；可先给不依赖该信息的部分。遇到模糊诉求、个人化决策、连续追问或话术请求时，读取 [对话与诉求分析指南](references/conversation-guide.md)。
2. 识别实体，不要把北大通班、北大智班、清华通班、姚班、无穹书院、智能学院和人工智能研究院混为一谈。遇到“人工智能实验班”“AI班”“智能班”“通班”等不唯一叫法，给出候选全称和建设单位，再请用户确认；可同时检索多组定义作为依据。
3. 将问题分到一个或多个 `scope`：`pku-general`、`yuanpei`、`tongban`、`ai-discipline`、`thu-general`、`thu-ai-cs`、`cross-school-comparison`；再确定 `stage`：`undergraduate`、`master`、`doctoral`、`summer-camp` 或 `general`。
4. 判断时效：
   - `stable`：组织沿革、项目全称、培养定位等稳定背景。
   - `live-index`：持续更新的官网入口或通知索引。
   - `current-cycle`：明确适用于某一招生年度或年级。
   - `historical`：已结束或仅供历史比较的材料。
5. 运行检索工具并严格按返回顺序处理：先读 `local_results` 中的本地补充资料及 `usage_limit`，再读 `results` 中的北大官方来源。对清华项目或官方库未覆盖的事实，随后联网查找相应学校、院系或书院的官方原页。需要时读取 [领域指南](references/domain-guide.md) 和 [回答政策](references/answer-policy.md)。
6. 本地库用于发现项目背景、比较维度、个人经验和待核说法，不是事实裁决终点。对名额、人数、截止日期、分数、资格、报名、录取、培养方案、课程、推免、去向、导师、学费、校区、联系方式、夏令营或“今年/现在/最新”等动态事实，必须打开当前官方页面再次核验。
7. 若没有当前官方依据，明确说“目前无法从已核验的现行文件确认”，给出最接近的官方入口，并将旧材料标为“历史参考”；不得从往年规则外推。
8. 直接回答，标明时间口径并附可点击的官方原页。必要时分成“已证实”“历史参考”“待核实”，不要堆砌无关链接。

## 使用工具

从任意工作目录运行：

```bash
python3 /path/to/pku-ai-admissions/scripts/search_sources.py '无穹书院课程和通班有什么区别' --json
python3 /path/to/pku-ai-admissions/scripts/search_sources.py '通班现在还招生吗，申请条件是什么' --json
python3 /path/to/pku-ai-admissions/scripts/search_sources.py '智能学院2027研究生招生指南' --scope ai-discipline --stage doctoral
```

`local_results` 始终先于官方 `results` 输出。每个本地结果包含原文件名、页码或段落、SHA-256、证据类型、材料时间、立场、可信度和使用限制。`internal-talking-points`、`anecdote`、`opinion` 与 `dynamic-unverified` 不能直接变成事实答案。

关注返回的 `guards`：

- `requires_live_check`：打开当前官方原页核验动态事实。
- `needs_clarification`：先区分通班与智班。
- `historical_only_risk`：通班现行问题只找到历史规则，不得外推。
- `summer_camp_not_admission`：明确夏令营状态不等于录取。
- `entity_confusion`：分别界定多个易混实体。
- `multi_unit_doctoral_route`：同时核对北大研招网和实际招生院系的当年细则。

检验资料库和检索行为：

```bash
python3 /path/to/pku-ai-admissions/scripts/verify_sources.py --as-of YYYY-MM-DD
python3 /path/to/pku-ai-admissions/scripts/verify_local_knowledge.py --as-of YYYY-MM-DD
python3 /path/to/pku-ai-admissions/scripts/verify_sources.py --as-of YYYY-MM-DD --check-links
python3 /path/to/pku-ai-admissions/scripts/eval_retrieval.py
```

默认核验不联网、无副作用；`--check-links` 才发起并发 URL 探测。联网探测遇到 403 可能是站点反自动化限制，应在浏览器中复核，而不是直接判定页面不存在。

## 坚守事实边界

- 将 2021 年通班简章只作为历史锚点。可以用它确认项目全称及 2021 年规则，不能据此声称当前仍面向同一对象、仍招不超过 25 人或沿用相同日程。
- 将智班的稳定培养定位与具体年级选拔分开。面向“2025级”的通知不是面向所有高考考生的独立统招简章。
- 将元培的自主选择专业表述为在教学资源与培养要求条件下进行，不能写成“任何专业无条件任选”。
- 将北大整体招生路径、校内项目遴选、转专业、专业分流、夏令营、推免与正式录取分别说明。
- 询问人工智能研究院博士招生时，不要假定研究院是唯一报名单位；按当年专业目录核对依托院系与报名路径。
- 不根据新闻报道、毕业典礼、培养方案或学术活动推断当前招生名额与资格。
- 不把无穹宣传材料中的培养设想写成已经验证的成效；注意“可能合作企业”等条件语。
- 不把“手撕”材料、内部招生策略、匿名树洞、个人文章中的分数、人数、去向、薪资或优劣结论写成客观事实。
- 比较北大和清华项目时，先拆成进入路径、课程结构、导师机制、科研准入、培养归属、推免/升学、风险偏好等可核维度，不输出“必然更好”或“稳进”的结论。

## 组织答案

优先使用下面的紧凑结构：

```text
结论（注明“截至 YYYY-MM-DD”或“适用于 YYYY 招生年度”）

已证实：稳定事实或现行文件明确内容。
历史参考：仅当旧材料有助于理解时提供，并写清年份。
待核实：缺失的现行细则，以及用户应查看的官方入口。

官方来源：紧邻对应结论给出原页链接。
```

若问题本身含错误前提，先纠正前提，再回答真实问题。若用户提供个人成绩、竞赛经历或身份，只说明需对照的官方条款，不承诺录取概率。

编写或审核多轮招生咨询示范时，读取 [对话示范评审标准](references/dialogue-rubric.md)；只有通过该标准的示范才应作为 Skill 参考材料。
