# Regression Matrix（本地 Compose 环境回归矩阵：必须全量 PASS，0 fail）

> 1. 仅记录当前真实实现，不要预填伪接口或目标态接口。
> 2. `Status` 允许值：`TODO` / `PASS` / `FAIL`。
> 3. 新增或未执行项默认填写 `TODO`，不得预填 `PASS`。
> 4. `PASS` 只允许在真实执行后填写，且 `Evidence` 不得保留占位符。
> 5. `python3 docs/tools/autopipeline/ap.py check-matrix` 会把非 `PASS` 行和占位符证据视为未完成。

| ID | Area | Endpoint/Feature | Test Type | Steps / Command | Expected | Status(TODO/PASS/FAIL) | Evidence |
|---|---|---|---|---|---|---|---|
| R-001 | API | <Endpoint or feature> | <smoke/regression/manual> | <command or manual steps> | <expected result> | TODO | <fill-with-log-path-screenshot-or-report> |
