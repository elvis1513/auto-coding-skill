# Security Baseline（最低门槛）

- secrets 不入库：targets.yaml（本地）或环境变量
- 写接口必须：输入校验、审计日志、反滥用
- 依赖审计：高危依赖必须处理或 ADR 解释
