# Mission (Follow Order) API Documentation

> **Base URL:** `http://localhost:8000/api`
> **Auth:** Tất cả endpoints yêu cầu `Authorization: Bearer <token>`
> **Quyền:** Admin only

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Enums mới](#2-enums-mới)
3. [Account: follow_active](#3-account-follow_active)
4. [Settings mới](#4-settings-mới)
5. [Mission Endpoints](#5-mission-endpoints)
6. [Luồng hoạt động](#6-luồng-hoạt-động)
7. [DB Migration](#7-db-migration)

---

## 1. Tổng quan

Mission (Follow Order) là tính năng tự động hóa **follow order** trên DSJ Exchange. Khác với Task thông thường (nhập mã đơn hàng), Mission thực hiện flow **xác nhận follow → done → completed**.

**Khác biệt so với Task:**

| | Task | Mission |
|---|---|---|
| `task_type` | `task` | `mission` |
| Flow tự động | Nhập order code → confirm | Follow confirm → done → completed |
| Input | `task_code` (= order code) | `account_ids` (bắt buộc), `task_code` tự sinh |
| Account chọn | Tùy chọn (mặc định = tất cả) | **Bắt buộc** chọn từ accounts có `follow_active = true` |
| Quyền | Admin, Staff, Customer | **Admin only** |
| Trang UI | Trang Task hiện tại | Trang mới riêng biệt |

---

## 2. Enums mới

### TaskType

| Giá trị   | Mô tả                     |
|-----------|----------------------------|
| `task`    | Task thường (mặc định)      |
| `mission` | Follow order mission        |

### TaskStatus (mở rộng)

| Giá trị     | Mô tả                                    |
|-------------|--------------------------------------------|
| `pending`   | Đã tạo, chuẩn bị chạy                       |
| `scheduled` | Đã lên lịch, chờ đến `scheduled_at` để chạy |
| `running`   | Đang chạy automation                     |
| `completed` | Hoàn thành                                |
| `failed`    | Thất bại hoặc bị hủy                     |

> Cột `task_type` trong bảng `tasks`. Các API task hiện tại tự động filter `task_type = "task"` nên **không ảnh hưởng UI frontend cũ**.

---

## 3. Account: follow_active

Mỗi account có field `follow_active` (boolean, mặc định `true`). Chỉ accounts có `follow_active = true` mới được chọn khi tạo mission.

### 3.1. Lấy accounts được phép follow

#### `GET /api/accounts/follow-active`

**Quyền:** Admin only

Trả về danh sách accounts có `follow_active = true`. Frontend dùng API này để hiển danh sách chọn khi tạo mission.

**Response:** `200 OK`
```json
[
  {
    "id": 1,
    "account_code": "ACC001",
    "email": "user1@dsj.com",
    "owner_id": 3,
    "follow_active": true
  }
]
```

### 3.2. Bật/tắt follow cho account

#### `PUT /api/accounts/{account_id}`

**Quyền:** Admin, Staff

**Request Body:**
```json
{
  "follow_active": false
}
```

**Response:** `200 OK` — `AccountResponse` với `follow_active` đã cập nhật.

> **Lưu ý:** Khi tạo mission với `account_ids`, hệ thống sẽ tự động lọc chỉ lấy accounts có `follow_active = true`. Accounts bị tắt sẽ bị bỏ qua.

---

## 4. Settings mới

### 4.1. Lấy Follow Settings

#### `GET /api/settings/follow`

**Quyền:** Admin only

**Response:**
```json
{
  "follow_confirm_text": "Confirm follow order",
  "follow_done_text": "Done",
  "follow_completed_text": "Follow order completed"
}
```

### 4.2. Cập nhật từng Setting

#### `PUT /api/settings/{key}`

**Quyền:** Admin only

Sử dụng API settings hiện có. Các key mới:

| Key | Default | Mô tả |
|-----|---------|--------|
| `follow_confirm_text` | `Confirm follow order` | Text nút xác nhận follow order |
| `follow_done_text` | `Done` | Text nút Done/OK sau khi confirm |
| `follow_completed_text` | `Follow order completed` | Text hiển thị khi follow thành công |

**Request Body:**
```json
{
  "value": "New text value"
}
```

**Response:** `200 OK`
```json
{
  "key": "follow_confirm_text",
  "value": "New text value",
  "description": "Text nút xác nhận follow order",
  "updated_at": "2026-04-04T12:00:00"
}
```

### 4.3. Lấy tất cả Settings

#### `GET /api/settings`

**Quyền:** Admin only

Response trả về tất cả settings bao gồm 3 follow settings mới (cùng format hiện tại).

---

## 5. Mission Endpoints

### 5.1. Tạo Mission

#### `POST /api/missions`

Tạo mission follow order mới. Mã mission (`task_code`) được tự sinh theo format `MISSION-YYYYMMDD-HHmmss`.

- **Không có `scheduled_at`**: Chạy ngay lập tức (status = `pending`)
- **Có `scheduled_at`**: Lên lịch chạy (status = `scheduled`), server tự động chạy khi đến giờ

**Request Body:**
```json
{
  "account_ids": [1, 3, 5],
  "headless": true,
  "scheduled_at": "2026-04-05T08:00:00+07:00"
}
```

| Field | Type | Required | Default | Mô tả |
|-------|------|----------|---------|--------|
| `account_ids` | int[] | ✅ | - | Danh sách ID account cần follow (chỉ lấy `follow_active = true`) |
| `headless` | bool | ❌ | `true` | Chạy browser ẩn hay hiện |
| `scheduled_at` | datetime | ❌ | `null` | Thời điểm chạy (ISO 8601 với timezone). `null` = chạy ngay |

**Response:** `200 OK`
```json
{
  "id": 10,
  "task_code": "MISSION-20260404-100530",
  "status": "scheduled",
  "total_accounts": 3,
  "success_count": 0,
  "failed_count": 0,
  "total_balance": 0,
  "created_by": 1,
  "scheduled_at": "2026-04-05T08:00:00+07:00",
  "created_at": "2026-04-04T10:00:00",
  "updated_at": "2026-04-04T10:00:00"
}
```

**Errors:**
- `400` — Không tìm thấy account hợp lệ (kiểm tra `follow_active`)
- `500` — Lỗi tạo mission

---

### 5.2. Danh sách Missions

#### `GET /api/missions`

**Query Params:**

| Param | Type | Default | Mô tả |
|-------|------|---------|--------|
| `page` | int | `1` | Trang hiện tại |
| `page_size` | int | `5` | Số item/trang (max 100) |
| `status` | string | - | Filter theo status (`pending`, `running`, `completed`, `failed`) |

**Response:** `200 OK`
```json
{
  "data": [
    {
      "id": 10,
      "task_code": "FOLLOW-20260404",
      "status": "completed",
      "total_accounts": 3,
      "success_count": 2,
      "failed_count": 1,
      "total_balance": 150000,
      "created_by": 1,
      "created_at": "2026-04-04T10:00:00",
      "updated_at": "2026-04-04T10:05:00",
      "details": [
        {
          "id": 100,
          "account_code": "ACC001",
          "email": "user1@example.com",
          "balance": 75000,
          "status": "success",
          "result_message": "Thành công",
          "screenshot_path": "screenshots/ACC001_follow_20260404.png"
        },
        {
          "id": 101,
          "account_code": "ACC002",
          "email": "user2@example.com",
          "balance": 75000,
          "status": "success",
          "result_message": "Thành công",
          "screenshot_path": null
        },
        {
          "id": 102,
          "account_code": "ACC003",
          "email": "user3@example.com",
          "balance": null,
          "status": "failed",
          "result_message": "Timeout waiting for confirm button",
          "screenshot_path": "screenshots/ACC003_follow_error.png"
        }
      ]
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 5,
    "total_items": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  }
}
```

---

### 5.3. Chi tiết Mission

#### `GET /api/missions/{mission_id}`

**Response:** `200 OK` — Cùng format 1 item trong `data[]` ở API danh sách.

**Errors:**
- `404` — Mission not found

---

### 5.4. Hủy Mission

#### `POST /api/missions/{mission_id}/cancel`

Hủy mission đang chạy.

**Response:** `200 OK`
```json
{
  "message": "Mission cancelled"
}
```

**Errors:**
- `404` — Mission not found
- `400` — Mission không đang chạy

---

### 5.5. Retry tất cả Failed

#### `POST /api/missions/{mission_id}/retry-all`

Chạy lại tất cả accounts bị failed trong mission.

**Query Params:**

| Param | Type | Default | Mô tả |
|-------|------|---------|--------|
| `headless` | bool | `true` | Browser ẩn/hiện |

**Response:** `200 OK`
```json
{
  "message": "Retrying 2 failed accounts",
  "count": 2
}
```

Nếu không có failed:
```json
{
  "message": "No failed accounts to retry",
  "count": 0
}
```

**Errors:**
- `404` — Mission not found
- `400` — Mission đang chạy

---

### 5.6. Retry một Account

#### `POST /api/missions/{mission_id}/retry/{detail_id}`

Chạy lại một account cụ thể.

**Query Params:**

| Param | Type | Default | Mô tả |
|-------|------|---------|--------|
| `headless` | bool | `true` | Browser ẩn/hiện |

**Response:** `200 OK`
```json
{
  "message": "Retrying account ACC001"
}
```

**Errors:**
- `404` — Mission not found
- `404` — Detail not found
- `400` — Mission đang chạy
- `400` — Account không ở trạng thái failed/pending

---

### 5.7. Xóa Mission

#### `DELETE /api/missions/{mission_id}`

Xóa mission (bao gồm tất cả details).

**Response:** `200 OK`
```json
{
  "message": "Mission FOLLOW-20260404 deleted successfully"
}
```

**Errors:**
- `404` — Mission not found
- `400` — Không thể xóa mission đang chạy

---

## 6. Luồng hoạt động

### 6.1. Tạo & chạy Mission

**Chạy ngay (không có `scheduled_at`):**
```
Frontend                Backend
  │                       │
  ├─GET /accounts/        │
  │  follow-active──────>│
  │<──[accounts list]────│
  │                       │
  ├─POST /missions──────>│
  │  {account_ids:[1,3]}  │─ status=pending
  │                       │─ Chạy ngay background
  │<──200 {status:pending}│
```

**Lên lịch (có `scheduled_at`):**
```
Frontend                Backend                     Scheduler (30s loop)
  │                       │                              │
  ├─POST /missions──────>│                              │
  │  {account_ids:[1,3],  │─ status=scheduled            │
  │   scheduled_at:       │─ Lưu vào DB, chưa chạy      │
  │   "2026-04-05T08:00"} │                              │
  │<──200 {scheduled}────│                              │
  │                       │                              │
  │                       │     ... đến giờ ...           │
  │                       │                              │
  │                       │<── Check scheduled_at <= now  │
  │                       │── status=pending → run_task() │
  │                       │                              │
  │  (poll GET /missions/{id})                           │
  │<──200 {details[]}────│                              │
```

### 6.2. Retry Flow

```
Frontend                    Backend
  │                           │
  ├─POST /retry-all──────────>│
  │  hoặc /retry/{detail_id} │
  │                           │─ Reset failed → pending
  │                           │─ Background: chạy lại automation
  │<──200 {message, count}───│
```

### 6.3. Settings Flow

```
Frontend                    Backend
  │                           │
  ├─GET /settings/follow─────>│
  │<──{confirm, done, text}──│
  │                           │
  │─PUT /settings/follow_confirm_text─>│
  │  {value: "Xác nhận"}     │─ Cập nhật DB + clear cache
  │<──200 {key, value}───────│
```

---

## 7. DB Migration

Chạy SQL này trên production PostgreSQL **trước khi deploy version mới**:

```sql
ALTER TABLE tasks ADD COLUMN task_type VARCHAR(20) NOT NULL DEFAULT 'task';
ALTER TABLE tasks ADD COLUMN scheduled_at TIMESTAMPTZ NULL;
ALTER TABLE tasks ADD COLUMN headless BOOLEAN NOT NULL DEFAULT true;
ALTER TABLE accounts ADD COLUMN follow_active BOOLEAN NOT NULL DEFAULT true;
```

> - Tất cả tasks hiện tại sẽ tự động có `task_type = 'task'`, `headless = true`.
> - Tất cả accounts hiện tại sẽ tự động có `follow_active = true`.
> - Settings mới sẽ tự seed khi server khởi động.
> - Scheduler tự động chạy khi server start, kiểm tra mỗi 30 giây.

---

## Tổng hợp Endpoints

| Method | Endpoint | Quyền | Mô tả |
|--------|----------|-------|--------|
| GET | `/api/accounts/follow-active` | Admin | Lấy accounts có follow_active=true |
| PUT | `/api/accounts/{id}` | Admin/Staff | Bật/tắt follow_active |
| GET | `/api/settings/follow` | Admin | Lấy follow settings |
| PUT | `/api/settings/follow_confirm_text` | Admin | Cập nhật confirm text |
| PUT | `/api/settings/follow_done_text` | Admin | Cập nhật done text |
| PUT | `/api/settings/follow_completed_text` | Admin | Cập nhật completed text |
| POST | `/api/missions` | Admin | Tạo mission (auto-gen task_code) |
| GET | `/api/missions` | Admin | Danh sách missions |
| GET | `/api/missions/{id}` | Admin | Chi tiết mission |
| POST | `/api/missions/{id}/cancel` | Admin | Hủy mission |
| POST | `/api/missions/{id}/retry-all` | Admin | Retry tất cả failed |
| POST | `/api/missions/{id}/retry/{detail_id}` | Admin | Retry 1 account |
| DELETE | `/api/missions/{id}` | Admin | Xóa mission |
