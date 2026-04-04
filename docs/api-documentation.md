# DSJ Automation API Documentation v2.1

> **Base URL:** `http://localhost:8000/api`
> **Swagger UI:** `http://localhost:8000/docs`
> **Default Admin:** `admin@dsj.com` / `admin123`

---

## Mục lục

1. [Authentication](#1-authentication)
2. [Enums & Constants](#2-enums--constants)
3. [Auth Endpoints](#3-auth-endpoints)
4. [User Endpoints](#4-user-endpoints)
5. [Account Endpoints](#5-account-endpoints)
6. [Task Endpoints](#6-task-endpoints)
7. [Task Action Endpoints](#7-task-action-endpoints)
8. [Statistics Endpoints](#8-statistics-endpoints)
9. [Settings Endpoints](#9-settings-endpoints)
10. [System Endpoints](#10-system-endpoints)
11. [SSE (Server-Sent Events)](#11-sse-server-sent-events)
12. [Error Handling](#12-error-handling)
13. [Screenshots](#13-screenshots)

---

## 1. Authentication

Tất cả endpoint (trừ `POST /api/auth/login` và `GET /api/health`) đều yêu cầu **Bearer Token** trong header:

```
Authorization: Bearer <access_token>
```

Token được trả về từ `POST /api/auth/login`, hết hạn sau **1440 phút (24 giờ)** (cấu hình qua `ACCESS_TOKEN_EXPIRE_MINUTES`).

**JWT Payload:**
```json
{
  "sub": "1",        // user ID (string)
  "role": "admin",   // UserRole
  "exp": 1712000000  // Unix timestamp
}
```

**Rate Limiting:** Endpoint login bị giới hạn **10 request/phút** theo IP.

---

## 2. Enums & Constants

### UserRole

| Giá trị    | Mô tả                                          |
|------------|-------------------------------------------------|
| `admin`    | Toàn quyền: quản lý users, accounts, tasks, settings |
| `staff`    | Quản lý accounts, tasks. Không quản lý users/settings |
| `customer` | Chỉ xem accounts/tasks/thống kê thuộc về mình  |

### TaskStatus

| Giá trị     | Mô tả                                    |
|-------------|-------------------------------------------|
| `pending`   | Task đã tạo, chưa chạy                   |
| `scheduled` | Đã lên lịch, chờ đến `scheduled_at` để chạy |
| `running`   | Đang chạy automation                     |
| `completed` | Hoàn thành (có thể có failed)            |
| `failed`    | Thất bại hoặc bị hủy                    |

### ResultStatus (trạng thái từng account trong task)

| Giá trị   | Mô tả                           |
|-----------|----------------------------------|
| `pending` | Chưa xử lý                      |
| `running` | Đang chạy automation cho account |
| `success` | Thành công                       |
| `failed`  | Thất bại                        |

### System Setting Keys

| Key           | Type   | Default      | Mô tả                                        |
|---------------|--------|--------------|-----------------------------------------------|
| `batch_size`  | int    | `2`          | Số account chạy đồng thời trong 1 batch      |
| `max_retries` | int    | `2`          | Số lần auto-retry cho account thất bại        |
| `site_domain` | string | `dsj079.com` | Domain website DSJ để chạy automation         |
| `follow_confirm_text` | string | `Confirm follow order` | Text nút xác nhận follow order |
| `follow_done_text` | string | `Done` | Text nút Done sau khi confirm follow |
| `follow_completed_text` | string | `Follow order completed` | Text hiển thị khi follow thành công |

### TaskType

| Giá trị   | Mô tả                     |
|-----------|----------------------------|
| `task`    | Task thường (mặc định)      |
| `mission` | Follow order mission        |

> Xem chi tiết Mission API tại [api-missions.md](api-missions.md)

---

## 3. Auth Endpoints

### POST `/api/auth/login`

Đăng nhập và nhận JWT token.

**Rate Limit:** 10 request/phút

**Request Body:**
```json
{
  "email": "admin@dsj.com",
  "password": "admin123"
}
```

**Response `200`:**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

**Errors:**
| Status | Detail                            |
|--------|-----------------------------------|
| 401    | Email hoặc mật khẩu không đúng   |
| 403    | Tài khoản đã bị vô hiệu hóa     |
| 429    | Rate limit exceeded               |

---

### GET `/api/auth/me`

Lấy thông tin user hiện tại.

**Requires:** Authenticated

**Response `200`:**
```json
{
  "id": 1,
  "email": "admin@dsj.com",
  "full_name": "Administrator",
  "role": "admin",
  "is_active": true,
  "created_at": "2026-04-02T10:00:00+00:00"
}
```

---

## 4. User Endpoints

> **Tất cả endpoint trong section này yêu cầu role `admin`**

### GET `/api/users`

Lấy danh sách users.

**Query Parameters:**
| Param  | Type | Default | Mô tả              |
|--------|------|---------|---------------------|
| `skip` | int  | 0       | Số record bỏ qua   |
| `limit`| int  | 100     | Số record tối đa    |

**Response `200`:** `UserResponse[]`
```json
[
  {
    "id": 1,
    "email": "admin@dsj.com",
    "full_name": "Administrator",
    "role": "admin",
    "is_active": true,
    "created_at": "2026-04-02T10:00:00+00:00"
  }
]
```

---

### GET `/api/users/{user_id}`

Lấy thông tin một user.

**Response `200`:** `UserResponse`

**Errors:**
| Status | Detail         |
|--------|----------------|
| 404    | User not found |

---

### POST `/api/users`

Tạo user mới.

**Request Body:**
```json
{
  "email": "staff@dsj.com",
  "password": "securepass",
  "full_name": "Staff User",
  "role": "staff"
}
```

| Field      | Type   | Required | Default    | Mô tả                                |
|------------|--------|----------|------------|---------------------------------------|
| `email`    | string | ✅       |            | Email đăng nhập (unique)              |
| `password` | string | ✅       |            | Mật khẩu                             |
| `full_name`| string | ✅       |            | Tên hiển thị                         |
| `role`     | string | ❌       | `customer` | `admin` \| `staff` \| `customer`     |

**Response `201`:** `UserResponse`

**Errors:**
| Status | Detail               |
|--------|----------------------|
| 400    | Invalid role         |
| 400    | Email already exists |

---

### PUT `/api/users/{user_id}`

Cập nhật thông tin user. Chỉ gửi các field cần thay đổi.

**Request Body:**
```json
{
  "full_name": "Updated Name",
  "role": "staff",
  "is_active": false
}
```

| Field       | Type    | Mô tả                            |
|-------------|---------|-----------------------------------|
| `email`     | string? | Email mới (unique)                |
| `full_name` | string? | Tên hiển thị mới                  |
| `role`      | string? | `admin` \| `staff` \| `customer` |
| `is_active` | bool?   | Vô hiệu hóa / kích hoạt         |

**Response `200`:** `UserResponse`

**Errors:**
| Status | Detail               |
|--------|----------------------|
| 400    | Invalid role         |
| 400    | Email already exists |
| 404    | User not found       |

---

### DELETE `/api/users/{user_id}`

Xóa user. Không thể xóa chính mình.

**Response `200`:**
```json
{ "message": "User deleted successfully" }
```

**Errors:**
| Status | Detail                |
|--------|-----------------------|
| 400    | Cannot delete yourself|
| 404    | User not found        |

---

### POST `/api/users/change-password`

Đổi mật khẩu. **Không yêu cầu role cụ thể** — bất kỳ user đã đăng nhập nào cũng dùng được.

**Request Body:**
```json
{
  "current_password": "oldpass",
  "new_password": "newpass"
}
```

**Response `200`:**
```json
{ "message": "Password changed successfully" }
```

**Errors:**
| Status | Detail                         |
|--------|--------------------------------|
| 400    | Mật khẩu hiện tại không đúng  |

---

## 5. Account Endpoints

### GET `/api/accounts`

Lấy danh sách tài khoản DSJ.

**Permission:**
- `admin`, `staff`: Xem tất cả
- `customer`: Chỉ xem accounts thuộc về mình (`owner_id = current_user.id`)

**Query Parameters:**
| Param  | Type | Default | Mô tả            |
|--------|------|---------|-------------------|
| `skip` | int  | 0       | Số record bỏ qua |
| `limit`| int  | 100     | Số record tối đa  |

**Response `200`:** `AccountResponse[]`
```json
[
  {
    "id": 1,
    "account_code": "ACC001",
    "email": "user@dsj.com",
    "owner_id": 3,
    "follow_active": true
  }
]
```

> **Lưu ý:** `password` **không bao giờ** trả về trong response.

---

### GET `/api/accounts/follow-active`

Lấy danh sách accounts có `follow_active = true`. **Requires:** `admin`

Dùng cho UI tạo mission — chỉ hiện accounts được phép chạy follow order.

**Response `200`:** `AccountResponse[]`
```json
[
  {
    "id": 1,
    "account_code": "ACC001",
    "email": "user@dsj.com",
    "owner_id": 3,
    "follow_active": true
  }
]
```

---

### GET `/api/accounts/{account_id}`

Lấy thông tin một account.

**Permission:**
- `admin`, `staff`: Xem bất kỳ
- `customer`: Chỉ xem account có `owner_id` = mình

**Response `200`:** `AccountResponse`

**Errors:**
| Status | Detail                   |
|--------|--------------------------|
| 403    | Insufficient permissions |
| 404    | Account not found        |

---

### POST `/api/accounts`

Thêm tài khoản mới. **Requires:** `admin` hoặc `staff`

**Request Body:**
```json
{
  "account_code": "ACC002",
  "email": "newuser@dsj.com",
  "password": "accountpass",
  "owner_id": 3
}
```

| Field          | Type   | Required | Mô tả                              |
|----------------|--------|----------|-------------------------------------|
| `account_code` | string | ✅       | Mã tài khoản (unique)              |
| `email`        | string | ✅       | Email đăng nhập DSJ (unique)       |
| `password`     | string | ✅       | Mật khẩu (sẽ được mã hóa Fernet)  |
| `owner_id`     | int?   | ❌       | ID user sở hữu (cho customer)     |
| `follow_active`| bool   | ❌       | Cho phép chạy follow order (mặc định `true`) |

**Response `200`:** `AccountResponse`

**Errors:**
| Status | Detail                     |
|--------|----------------------------|
| 400    | Account code already exists|
| 400    | Email already exists       |
| 400    | Owner user not found       |

---

### PUT `/api/accounts/{account_id}`

Sửa tài khoản. **Requires:** `admin` hoặc `staff`. Chỉ gửi field cần thay đổi.

**Request Body:**
```json
{
  "email": "updated@dsj.com",
  "password": "newpass"
}
```

| Field          | Type   | Mô tả                              |
|----------------|--------|-------------------------------------|
| `account_code` | string?| Mã tài khoản mới (unique)          |
| `email`        | string?| Email mới (unique)                 |
| `password`     | string?| Mật khẩu mới (sẽ mã hóa)         |
| `owner_id`     | int?   | ID user sở hữu mới                |
| `follow_active`| bool?  | Bật/tắt follow order cho account   |

**Response `200`:** `AccountResponse`

**Errors:**
| Status | Detail                     |
|--------|----------------------------|
| 400    | Account code already exists|
| 400    | Email already exists       |
| 404    | Account not found          |

---

### DELETE `/api/accounts/{account_id}`

Xóa tài khoản. **Requires:** `admin` hoặc `staff`

**Response `200`:**
```json
{ "message": "Account deleted successfully" }
```

**Errors:**
| Status | Detail          |
|--------|-----------------|
| 404    | Account not found|

---

## 6. Task Endpoints

### POST `/api/tasks`

Tạo task mới và tự động khởi chạy automation trong background. **Requires:** `admin` hoặc `staff`

**Request Body:**
```json
{
  "task_code": "TASK-20260402",
  "account_ids": [1, 2, 5],
  "headless": true
}
```

| Field         | Type   | Required | Default | Mô tả                                              |
|---------------|--------|----------|---------|-----------------------------------------------------|
| `task_code`   | string | ✅       |         | Mã task (unique) — thường là order code             |
| `account_ids` | int[]? | ❌       | null    | Danh sách account IDs. `null` = chạy **tất cả** accounts |
| `headless`    | bool   | ❌       | true    | `true` = ẩn trình duyệt, `false` = hiện browser    |

**Response `200`:** `TaskResponse`
```json
{
  "id": 1,
  "task_code": "TASK-20260402",
  "status": "pending",
  "total_accounts": 3,
  "success_count": 0,
  "failed_count": 0,
  "total_balance": 0.0,
  "created_by": 1,
  "created_at": "2026-04-02T10:30:00+00:00",
  "updated_at": null
}
```

> **Lưu ý:** Task sẽ chuyển sang `running` ngay sau khi response trả về. Dùng SSE stream để theo dõi progress realtime.

**Errors:**
| Status | Detail                  |
|--------|-------------------------|
| 400    | Task code already exists|
| 400    | No accounts available   |
| 500    | Failed to create task   |

---

### GET `/api/tasks`

Lấy danh sách tasks với phân trang. Mỗi task bao gồm chi tiết từng account.

**Permission:**
- `admin`, `staff`: Xem tất cả tasks
- `customer`: Chỉ xem tasks chứa accounts của mình, và chỉ thấy details của accounts mình

**Query Parameters:**
| Param       | Type   | Default | Mô tả                                                  |
|-------------|--------|---------|---------------------------------------------------------|
| `page`      | int    | 1       | Trang hiện tại (min: 1)                                |
| `page_size` | int    | 5       | Số task mỗi trang (min: 1, max: 100)                  |
| `status`    | string?| null    | Lọc theo TaskStatus: `pending`\|`running`\|`completed`\|`failed` |

**Response `200`:** `TaskListResponse`
```json
{
  "data": [
    {
      "id": 1,
      "task_code": "TASK-20260402",
      "status": "completed",
      "total_accounts": 3,
      "success_count": 2,
      "failed_count": 1,
      "total_balance": 150.5,
      "created_by": 1,
      "created_at": "2026-04-02T10:30:00+00:00",
      "updated_at": "2026-04-02T10:35:00+00:00",
      "details": [
        {
          "id": 1,
          "account_code": "ACC001",
          "email": "user1@dsj.com",
          "balance": 75.25,
          "status": "success",
          "result_message": "Thành công",
          "screenshot_path": "screenshots/ACC001_20260402_103200.png"
        },
        {
          "id": 2,
          "account_code": "ACC002",
          "email": "user2@dsj.com",
          "balance": 75.25,
          "status": "success",
          "result_message": "Thành công",
          "screenshot_path": null
        },
        {
          "id": 3,
          "account_code": "ACC003",
          "email": "user3@dsj.com",
          "balance": null,
          "status": "failed",
          "result_message": "Lỗi tại bước 'Xác nhận đăng nhập thành công': Timeout",
          "screenshot_path": "screenshots/ACC003_failed_verify_login.png"
        }
      ]
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 5,
    "total_items": 12,
    "total_pages": 3,
    "has_next": true,
    "has_prev": false
  }
}
```

---

### GET `/api/tasks/{task_id}`

Lấy chi tiết một task bao gồm tất cả details.

**Permission:** Tương tự GET `/api/tasks` — customer chỉ thấy details của accounts mình.

**Response `200`:** `TaskDetailResponse` (giống 1 item trong `data[]` ở trên)

**Errors:**
| Status | Detail                   |
|--------|--------------------------|
| 403    | Insufficient permissions |
| 404    | Task not found           |

---

### DELETE `/api/tasks/{task_id}`

Xóa task. **Requires:** `admin` hoặc `staff`. Không xóa được task đang `running`.

**Response `200`:**
```json
{ "message": "Task TASK-20260402 deleted successfully" }
```

**Errors:**
| Status | Detail                      |
|--------|-----------------------------|
| 400    | Cannot delete running task  |
| 404    | Task not found              |

---

### DELETE `/api/tasks/{task_id}/force`

Force xóa task bất kể trạng thái. **Requires:** `admin` only.

**Response `200`:**
```json
{ "message": "Task TASK-20260402 force deleted" }
```

**Errors:**
| Status | Detail          |
|--------|-----------------|
| 404    | Task not found  |

---

## 7. Task Action Endpoints

> **Tất cả endpoint trong section này yêu cầu role `admin` hoặc `staff`** (trừ stream)

### POST `/api/tasks/{task_id}/cancel`

Hủy task đang chạy. Task sẽ chuyển sang trạng thái `failed`.

**Response `200`:**
```json
{ "message": "Task cancelled" }
```

**Errors:**
| Status | Detail              |
|--------|---------------------|
| 400    | Task is not running |
| 404    | Task not found      |

---

### POST `/api/tasks/{task_id}/retry/{detail_id}`

Chạy lại một account cụ thể. Chỉ retry được account có status `failed` hoặc `pending`.

**Query Parameters:**
| Param     | Type | Default | Mô tả               |
|-----------|------|---------|----------------------|
| `headless`| bool | true    | Ẩn/hiện trình duyệt |

**Response `200`:**
```json
{ "message": "Retrying account ACC001" }
```

**Errors:**
| Status | Detail                                        |
|--------|-----------------------------------------------|
| 400    | Cannot retry while task is running            |
| 400    | Can only retry failed/pending. Current: success |
| 404    | Task not found                                |
| 404    | Task detail not found                         |

---

### POST `/api/tasks/{task_id}/retry-all`

Chạy lại tất cả accounts `failed` trong task.

**Query Parameters:**
| Param     | Type | Default | Mô tả               |
|-----------|------|---------|----------------------|
| `headless`| bool | true    | Ẩn/hiện trình duyệt |

**Response `200`:**
```json
{
  "message": "Retrying 5 failed accounts",
  "count": 5
}
```

Nếu không có account failed:
```json
{
  "message": "No failed accounts to retry",
  "count": 0
}
```

**Errors:**
| Status | Detail                     |
|--------|----------------------------|
| 400    | Task is already running    |
| 404    | Task not found             |

---

### POST `/api/tasks/{task_id}/resume`

Tiếp tục chạy task — xử lý tất cả accounts có status `pending` hoặc `failed`.

**Query Parameters:**
| Param     | Type | Default | Mô tả               |
|-----------|------|---------|----------------------|
| `headless`| bool | true    | Ẩn/hiện trình duyệt |

**Response `200`:**
```json
{
  "message": "Resuming with 8 accounts",
  "count": 8
}
```

Nếu không có account cần chạy:
```json
{
  "message": "No pending accounts to run",
  "count": 0
}
```

**Errors:**
| Status | Detail                  |
|--------|-------------------------|
| 400    | Task is already running |
| 404    | Task not found          |

---

### GET `/api/tasks/{task_id}/stream`

**SSE (Server-Sent Events)** — Stream realtime progress của task.

**Requires:** Authenticated (bất kỳ role)

**Response:** `text/event-stream`

Chi tiết tham khảo [Section 11: SSE](#11-sse-server-sent-events).

---

## 8. Statistics Endpoints

### GET `/api/statistics`

Lấy thống kê tổng quan.

**Permission:**
- `admin`, `staff`: Thống kê toàn bộ hệ thống
- `customer`: Thống kê chỉ accounts của mình

**Response `200`:**
```json
{
  "total_balance": 12500.75,
  "total_accounts": 50,
  "total_tasks": 15,
  "success_rate": 87.5
}
```

| Field            | Type  | Mô tả                                                  |
|------------------|-------|---------------------------------------------------------|
| `total_balance`  | float | Tổng balance từ tất cả task details thành công          |
| `total_accounts` | int   | Tổng số tài khoản DSJ (hoặc số accounts của customer)  |
| `total_tasks`    | int   | Tổng số tasks                                          |
| `success_rate`   | float | Tỷ lệ thành công (%) — 100.0 nếu chưa có kết quả     |

---

## 9. Settings Endpoints

### GET `/api/settings`

Lấy tất cả settings. **Requires:** `admin`

**Response `200`:** `SettingResponse[]`
```json
[
  {
    "key": "batch_size",
    "value": "2",
    "description": "Số account chạy đồng thời trong 1 batch",
    "updated_at": "2026-04-02T10:00:00+00:00"
  },
  {
    "key": "max_retries",
    "value": "2",
    "description": "Số lần retry tự động cho account thất bại",
    "updated_at": null
  },
  {
    "key": "site_domain",
    "value": "dsj079.com",
    "description": "Domain website DSJ để chạy automation",
    "updated_at": null
  }
]
```

---

### GET `/api/settings/automation`

Lấy settings automation dạng gọn. **Requires:** `admin` hoặc `staff`

**Response `200`:**
```json
{
  "batch_size": 2,
  "max_retries": 2,
  "site_domain": "dsj079.com"
}
```

---

### PUT `/api/settings/{key}`

Cập nhật một setting. **Requires:** `admin`

**Path Parameters:**
| Param | Type   | Mô tả                                            |
|-------|--------|---------------------------------------------------|
| `key` | string | Setting key: `batch_size` \| `max_retries` \| `site_domain` |

**Request Body:**
```json
{
  "value": "5"
}
```

**Response `200`:** `SettingResponse`

**Errors:**
| Status | Detail                             |
|--------|------------------------------------|
| 400    | Unknown setting key: xxx           |
| 400    | batch_size phải là số nguyên >= 1  |
| 400    | max_retries phải là số nguyên >= 1 |

---

## 10. System Endpoints

### GET `/api/health`

Health check. **Không cần authentication.**

**Response `200`:**
```json
{
  "status": "healthy",
  "timestamp": "2026-04-02T10:00:00+00:00"
}
```

---

## 11. SSE (Server-Sent Events)

### Endpoint: `GET /api/tasks/{task_id}/stream`

Kết nối SSE để theo dõi progress task realtime.

**Giới hạn:**
- **Max duration:** 10 phút — sau đó server tự đóng kết nối
- **Heartbeat:** Mỗi 15 giây gửi comment `: heartbeat` để giữ kết nối

**Frontend Example (JavaScript):**
```javascript
const token = "eyJhbGciOi...";
const eventSource = new EventSource(
  `http://localhost:8000/api/tasks/1/stream`,
  {
    headers: { "Authorization": `Bearer ${token}` }
  }
);

// Hoặc dùng fetch (recommended cho custom headers):
const response = await fetch(`/api/tasks/1/stream`, {
  headers: { "Authorization": `Bearer ${token}` }
});
const reader = response.body.getReader();
const decoder = new TextDecoder();
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const text = decoder.decode(value);
  // Parse SSE format: "data: {...}\n\n"
  const lines = text.split("\n");
  for (const line of lines) {
    if (line.startsWith("data: ")) {
      const data = JSON.parse(line.slice(6));
      console.log(data);
    }
  }
}
```

**Event Types:**

#### Progress Update
Gửi khi `success_count` hoặc `failed_count` thay đổi:
```json
{
  "task_id": 1,
  "status": "running",
  "total_accounts": 10,
  "success_count": 3,
  "failed_count": 1,
  "total_balance": 225.50,
  "progress": 40.0
}
```

| Field            | Type   | Mô tả                             |
|------------------|--------|------------------------------------|
| `task_id`        | int    | ID task                           |
| `status`         | string | TaskStatus hiện tại                |
| `total_accounts` | int    | Tổng số accounts                  |
| `success_count`  | int    | Số đã thành công                  |
| `failed_count`   | int    | Số đã thất bại                   |
| `total_balance`  | float  | Tổng balance hiện tại            |
| `progress`       | float  | Phần trăm hoàn thành (0-100)     |

#### Completed Event
Gửi khi task hoàn thành / thất bại (cuối cùng trước khi đóng stream):
```json
{
  "event": "completed",
  "status": "completed"
}
```

#### Timeout Event
Gửi khi stream quá 10 phút:
```json
{
  "event": "timeout",
  "message": "SSE connection timeout"
}
```

#### Error Event
```json
{
  "error": "Task not found"
}
```

---

## 12. Error Handling

### Response Format

Tất cả error đều trả về dạng:
```json
{
  "detail": "Error message here"
}
```

### Common HTTP Status Codes

| Status | Ý nghĩa                                           |
|--------|----------------------------------------------------|
| 200    | Thành công                                         |
| 201    | Tạo mới thành công (chỉ POST /api/users)          |
| 400    | Request không hợp lệ (validation error, conflict)  |
| 401    | Chưa đăng nhập hoặc token hết hạn                 |
| 403    | Không đủ quyền (role không phù hợp)               |
| 404    | Không tìm thấy resource                           |
| 422    | Validation error (Pydantic schema mismatch)        |
| 429    | Rate limit exceeded (chỉ endpoint login)           |
| 500    | Lỗi server                                        |

### Validation Error (422)
Khi request body không khớp schema:
```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

---

## 13. Screenshots

Screenshots được automation chụp khi task chạy, lưu tại server.

**Static File URL:** `http://localhost:8000/screenshots/{filename}`

Giá trị `screenshot_path` trong `TaskDetailItem` chứa đường dẫn relative (ví dụ: `screenshots/ACC001_20260402.png`). Frontend hiển thị:

```javascript
const screenshotUrl = `http://localhost:8000/${detail.screenshot_path}`;
// => http://localhost:8000/screenshots/ACC001_20260402.png
```

---

## Bảng tóm tắt Permission

| Endpoint                            | Method | Admin | Staff | Customer |
|-------------------------------------|--------|:-----:|:-----:|:--------:|
| `/api/auth/login`                   | POST   | -     | -     | -        |
| `/api/auth/me`                      | GET    | ✅    | ✅    | ✅       |
| `/api/users`                        | GET    | ✅    | ❌    | ❌       |
| `/api/users/{id}`                   | GET    | ✅    | ❌    | ❌       |
| `/api/users`                        | POST   | ✅    | ❌    | ❌       |
| `/api/users/{id}`                   | PUT    | ✅    | ❌    | ❌       |
| `/api/users/{id}`                   | DELETE | ✅    | ❌    | ❌       |
| `/api/users/change-password`        | POST   | ✅    | ✅    | ✅       |
| `/api/accounts`                     | GET    | ✅    | ✅    | ✅*      |
| `/api/accounts/{id}`                | GET    | ✅    | ✅    | ✅*      |
| `/api/accounts`                     | POST   | ✅    | ✅    | ❌       |
| `/api/accounts/{id}`                | PUT    | ✅    | ✅    | ❌       |
| `/api/accounts/{id}`                | DELETE | ✅    | ✅    | ❌       |
| `/api/tasks`                        | GET    | ✅    | ✅    | ✅*      |
| `/api/tasks/{id}`                   | GET    | ✅    | ✅    | ✅*      |
| `/api/tasks`                        | POST   | ✅    | ✅    | ❌       |
| `/api/tasks/{id}`                   | DELETE | ✅    | ✅    | ❌       |
| `/api/tasks/{id}/force`             | DELETE | ✅    | ❌    | ❌       |
| `/api/tasks/{id}/cancel`            | POST   | ✅    | ✅    | ❌       |
| `/api/tasks/{id}/retry/{detail_id}` | POST   | ✅    | ✅    | ❌       |
| `/api/tasks/{id}/retry-all`         | POST   | ✅    | ✅    | ❌       |
| `/api/tasks/{id}/resume`            | POST   | ✅    | ✅    | ❌       |
| `/api/tasks/{id}/stream`            | GET    | ✅    | ✅    | ✅       |
| `/api/statistics`                   | GET    | ✅    | ✅    | ✅*      |
| `/api/settings`                     | GET    | ✅    | ❌    | ❌       |
| `/api/settings/automation`          | GET    | ✅    | ✅    | ❌       |
| `/api/settings/{key}`               | PUT    | ✅    | ❌    | ❌       |
| `/api/health`                       | GET    | -     | -     | -        |

> **✅\*** = Chỉ xem dữ liệu thuộc về accounts của mình (filtered by `owner_id`)
