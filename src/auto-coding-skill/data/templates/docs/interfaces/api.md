# API Documentation（权威接口文档）

> 本文件为权威接口文档。任何接口新增/修改/废弃，都必须同步更新本文件，并在 `api-change-log.md` 追加记录。

## 1. 基本约定
- Base URL：
- Content-Type：
- 认证方式（如有）：
- 时区/时间格式：
- 分页/排序（如有）：
- 错误码规范：

## 2. Endpoint Index（目录）
| Method | Path | Summary | Auth | Request | Response |
|---|---|---|---|---|---|
| GET | /health | Health check | No | - | 200 OK |

## 3. Endpoints

### 3.1 GET /health
**Summary**: Health check

**Request**
- Headers: -
- Query: -
- Body: -

**Response**
- 200: OK
  - Example:
    ```json
    {"status":"ok"}
    ```

## 4. Changelog
- See `api-change-log.md`
