# Regression Matrix（按需回归记录，不是每个小改动的默认门禁）

> 1. 只记录真实执行过的回归项。
> 2. `Status` 允许值：`TODO` / `PASS` / `FAIL`。
> 3. 未执行项保持 `TODO`，不得预填 `PASS`。
> 4. 只有真实执行并具备证据时，才允许填写 `PASS`。
> 5. `check-matrix` 只在显式要求完整回归时使用，不作为默认小改动门禁。

| ID | Area | Endpoint/Feature | Test Type | Steps / Command | Expected | Status(TODO/PASS/FAIL) | Evidence |
|---|---|---|---|---|---|---|---|
| R-001 | <Area> | <Endpoint or feature> | <manual/smoke/regression> | <command or manual steps> | <expected result> | TODO | <real log path / screenshot / report> |
