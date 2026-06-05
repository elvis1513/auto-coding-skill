# Closure Log（默认轻量闭环记录：每个任务至少一条）

规则：
1) 每个任务完成后，至少追加一条闭环记录
2) `dev` 模式记录开发闭环：轻量门禁通过、已提交推送、Jenkins 已由 push 触发但不等待验证
3) `verify` 模式记录完整闭环：真实提交、Jenkins 构建、目标环境验证结果
4) Jenkins 失败后再修复的任务，应补充失败原因和修复提交
5) 这里是默认闭环文档；长 summary 只用于高风险或复盘任务

---

## <TASK_ID> — <Title> — YYYY-MM-DD HH:MM
- Task: <TASK_ID>
- Commit: <commit sha>
- Jenkins Build: <build url>
- Target Env: <env name / health url / page path>
- Verification: <health / key api / key page / business path>
- Result: DEV-CLOSED / PASS / FAIL / PARTIAL
- Follow-up: <none or todo>
- Jenkins Failure: <optional>
- Fix Commit: <optional>

---

继续在下方追加记录（不要删除历史记录）
