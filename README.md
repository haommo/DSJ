# DSJ Automation Backend

Backend API để quản lý và tự động hóa quy trình trên DSJ Exchange.

## 🚀 Tính năng

- ✅ API RESTful quản lý tài khoản (CRUD)
- ✅ Quản lý và chạy tasks automation
- ✅ Lưu trữ kết quả vào SQLite database
- ✅ Chạy automation trong background
- ✅ Dashboard thống kê
- ✅ Chụp screenshot kết quả

## 📁 Cấu trúc Project

```
DSJ/
├── main.py              # Entry point - khởi chạy server
├── api.py               # FastAPI endpoints
├── models.py            # Database models (SQLAlchemy)
├── schemas.py           # Pydantic schemas
├── database.py          # Database connection
├── automation_runner.py # Logic chạy automation
├── task_manager.py      # Quản lý tasks
├── automation.py        # Script automation đơn lẻ (legacy)
├── requirements.txt     # Dependencies
├── screenshots/         # Thư mục chứa screenshots
└── dsj_automation.db    # SQLite database (auto-generated)
```

## 🔧 Cài đặt

1. Cài đặt dependencies:
```bash
pip3 install -r requirements.txt
```

2. Cài đặt Chromium browser cho Playwright:
```bash
playwright install chromium
```

## ▶️ Chạy Server

```bash
python3 main.py
```

Hoặc với uvicorn:
```bash
uvicorn api:app --reload --host 0.0.0.0 --port 8000
```

Server sẽ chạy tại: http://localhost:8000

## 📖 API Documentation

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 🔌 API Endpoints

### 1. Quản lý tài khoản (Accounts)
| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/accounts` | Lấy danh sách tài khoản |
| GET | `/api/accounts/{id}` | Lấy thông tin tài khoản |
| POST | `/api/accounts` | Thêm tài khoản mới |
| PUT | `/api/accounts/{id}` | Sửa tài khoản |
| DELETE | `/api/accounts/{id}` | Xóa tài khoản |

**Account bao gồm:** `id`, `email`, `password`

### 2. Thống kê (Statistics)
| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/statistics` | Lấy thống kê tổng quan |

**Response:**
- `total_balance`: Tổng số dư
- `total_accounts`: Tổng tài khoản
- `total_tasks`: Tổng task
- `success_rate`: Tỷ lệ thành công (%)

### 3. Danh sách Task (Tasks)
| Method | Endpoint | Mô tả |
|--------|----------|-------|
| GET | `/api/tasks` | Lấy danh sách tasks |
| GET | `/api/tasks/{id}` | Lấy chi tiết task |
| POST | `/api/tasks` | Tạo task mới và chạy automation |
| POST | `/api/tasks/{id}/cancel` | Hủy task đang chạy |
| DELETE | `/api/tasks/{id}` | Xóa task |

**Mỗi Task bao gồm:**
- `task_code`: Mã task
- `created_at`: Ngày giờ
- `total_balance`: Tổng số dư
- `total_accounts`: Tổng số tài khoản chạy
- `success_count`: Số thành công
- `failed_count`: Số thất bại
- `status`: Trạng thái

**Chi tiết Task (GET /api/tasks/{id}):**
- `account_code`: Mã tài khoản
- `email`: Email
- `balance`: Số dư
- `status`: Trạng thái
- `result_message`: Kết quả
- `screenshot_path`: Hình ảnh

## 📝 Ví dụ sử dụng API

### 1. Thêm tài khoản mới
```bash
curl -X POST http://localhost:8000/api/accounts \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user1@example.com",
    "password": "your_password"
  }'
```

### 2. Lấy thống kê
```bash
curl http://localhost:8000/api/statistics
```

Response:
```json
{
  "total_balance": 6750.0,
  "total_accounts": 5,
  "total_tasks": 2,
  "success_rate": 100.0
}
```

### 3. Tạo task mới (chạy tất cả accounts)
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_code": "1BTEQ6KHU"
  }'
```

### 4. Tạo task với accounts cụ thể
```bash
curl -X POST http://localhost:8000/api/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "task_code": "2XYZABC99",
    "account_ids": [1, 2, 3]
  }'
```

### 5. Xem chi tiết task
```bash
curl http://localhost:8000/api/tasks/1
```

Response:
```json
{
  "id": 1,
  "task_code": "1BTEQ6KHU",
  "status": "completed",
  "total_accounts": 5,
  "success_count": 5,
  "failed_count": 0,
  "total_balance": 6757.15,
  "created_at": "2024-12-25T10:30:00",
  "results": [
    {
      "account_code": "AQPS7UO3IG00",
      "email": "user1@example.com",
      "balance": 1303.46,
      "status": "success",
      "result_message": "Thành công",
      "screenshot_path": "screenshots/success_user1_20241225_103500.png"
    }
  ]
}
```

## 🔄 Workflow

1. **Thêm accounts** vào database qua API
2. **Tạo task** với mã nhiệm vụ (task_code)
3. Backend tự động **chạy automation** cho từng account
4. Kết quả được **cập nhật realtime** vào database
5. Frontend có thể **poll API** để lấy trạng thái

## ⚙️ Cấu hình

Trong `automation_runner.py`, có thể điều chỉnh:
- `headless=True/False`: Ẩn/hiện browser
- `slow_mo=300`: Delay giữa các action (ms)
- Timeout cho các bước

## 📊 Database Schema

### Accounts
| Field | Type | Mô tả |
|-------|------|-------|
| id | Integer | ID tự động |
| email | String | Email đăng nhập |
| password | String | Mật khẩu |
| created_at | DateTime | Ngày tạo |

### Tasks
| Field | Type | Mô tả |
|-------|------|-------|
| id | Integer | ID tự động |
| task_code | String | Mã task |
| status | String | Trạng thái (pending/running/completed/failed) |
| total_accounts | Integer | Tổng số tài khoản chạy |
| success_count | Integer | Số thành công |
| failed_count | Integer | Số thất bại |
| total_balance | Float | Tổng số dư |
| created_at | DateTime | Ngày giờ tạo |

### TaskResults
| Field | Type | Mô tả |
|-------|------|-------|
| id | Integer | ID tự động |
| task_id | Integer | FK → Tasks |
| account_id | Integer | FK → Accounts |
| account_code | String | Mã tài khoản trên DSJ |
| balance | Float | Số dư |
| status | String | Trạng thái (pending/running/success/failed) |
| result_message | String | Kết quả |
| screenshot_path | String | Đường dẫn hình ảnh |
| created_at | DateTime | Ngày tạo |
| completed_at | DateTime | Ngày hoàn thành |
