# Field Asset Check-Out Service (REST API)

[![Python](https://img.shields.io/badge/Python-3.12%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Django](https://img.shields.io/badge/Django-5.2-green.svg)](https://www.djangoproject.com/)
[![DRF](https://img.shields.io/badge/DRF-3.15-red.svg)](https://www.django-rest-framework.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-blue.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-red.svg)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-5.3-green.svg)](https://docs.celeryq.dev/)
[![Tests](https://img.shields.io/badge/Tests-45%20Passed%20(100%25)-brightgreen.svg)](https://docs.pytest.org/)

Production-grade internal REST API for tracking physical field equipment checked out to and returned by field employees. Built with **Django 5**, **Django REST Framework (DRF)**, **PostgreSQL 15**, **Redis 7**, and **Celery**, enforcing strict database-level concurrency protection, single-query ORM aggregations, and periodic background worker tasks.

---

## Screen Recording

- **Loom / Video Walkthrough:** [https://www.loom.com/share/field-asset-checkout-service-walkthrough-demo](https://www.loom.com/share/field-asset-checkout-service-walkthrough-demo) *(Placeholder: Insert your Loom/Drive link here)*
- *Walkthrough covers: Docker startup, migrations, demo data seeding, check-out and return workflows, employee summary aggregation, overdue report, pytest execution (45 passing tests), and architectural discussion.*

---

## Quickstart & Setup Guide

### Method 1: Docker Compose (Recommended for Evaluators)

Clone the repository and run the entire stack (Django API, PostgreSQL 15, Redis 7, Celery Worker, Celery Beat) with a single command:

```bash
# 1. Build and start all services in the background
docker compose up --build -d

# 2. Populate demo data (assets, employees, checkouts, and evaluator credentials)
docker compose exec web python manage.py seed_demo_data

# 3. Verify service health
curl -s http://localhost:8000/api/v1/health/
```

*The API is now live at `http://localhost:8000/api/v1/`.*

---

### Method 2: Local Virtual Environment Setup

```bash
# 1. Clone repository
git clone https://github.com/R-ahul-patidar/field-asset-checkout-service.git
cd field-asset-checkout-service

# 2. Create and activate virtual environment
python -m venv .venv
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# On Linux / macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment configuration
cp .env.example .env

# 5. Run database migrations
python manage.py migrate

# 6. Seed demo data
python manage.py seed_demo_data

# 7. Start local development server
python manage.py runserver 8000
```

---

## Authentication & Evaluator Credentials

All endpoints under `/api/v1/` (except `/api/v1/health/`) require token authentication via the HTTP header:
```http
Authorization: Token <token_key>
```

### Pre-Seeded Evaluator Account:
- **Username:** `admin`
- **Password:** `adminpassword123`
- **Pre-Generated Token:** `2879de74d786d2420a4dcb18b7a2d11673b22211`

### Obtain / Refresh Token:
```bash
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "adminpassword123"}'
```

---

## API Endpoints & Usage Examples

### 1. Health Check (Unauthenticated)
```bash
curl -X GET http://localhost:8000/api/v1/health/
```
**Response (`200 OK`):**
```json
{
  "status": "healthy",
  "database": "connected"
}
```

---

### 2. List Assets (Filtered, Searched, Paginated)
Supports filtering by `?status=`, `?category=`, and text search `?search=` across asset name and tag.
```bash
curl -X GET "http://localhost:8000/api/v1/assets/?status=AVAILABLE&category=LAPTOP" \
  -H "Authorization: Token 2879de74d786d2420a4dcb18b7a2d11673b22211"
```
**Response (`200 OK`):**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 2,
      "asset_tag": "LAP-002",
      "name": "MacBook Pro 16 M3 Max",
      "category": "LAPTOP",
      "status": "AVAILABLE",
      "purchase_date": "2023-11-20",
      "created_at": "2026-08-21T08:16:04.123456Z",
      "updated_at": "2026-08-21T08:16:04.123456Z",
      "current_holder": null
    }
  ]
}
```

---

### 3. Retrieve Single Asset with Dynamic `current_holder`
Optimized with prefetching (`Prefetch`) to eliminate N+1 queries.
```bash
curl -X GET http://localhost:8000/api/v1/assets/1/ \
  -H "Authorization: Token 2879de74d786d2420a4dcb18b7a2d11673b22211"
```
**Response (`200 OK`):**
```json
{
  "id": 1,
  "asset_tag": "LAP-001",
  "name": "ThinkPad X1 Carbon Gen 11",
  "category": "LAPTOP",
  "status": "CHECKED_OUT",
  "purchase_date": "2023-05-10",
  "created_at": "2026-08-21T08:16:04.123456Z",
  "updated_at": "2026-08-21T08:16:04.123456Z",
  "current_holder": {
    "employee_code": "EMP-001",
    "name": "Sarah Connor"
  }
}
```

---

### 4. Check-Out Asset
Enforces business rules (Rules 1–5, 7, 8) with database row-level locking (`select_for_update()`).
```bash
curl -X POST http://localhost:8000/api/v1/checkouts/ \
  -H "Authorization: Token 2879de74d786d2420a4dcb18b7a2d11673b22211" \
  -H "Content-Type: application/json" \
  -d '{
    "asset_tag": "LAP-002",
    "employee_code": "EMP-003",
    "due_at": "2026-09-05T18:00:00Z"
  }'
```
**Response (`201 Created`):**
```json
{
  "id": 8,
  "asset": 2,
  "asset_tag": "LAP-002",
  "asset_name": "MacBook Pro 16 M3 Max",
  "employee": 3,
  "employee_code": "EMP-003",
  "employee_name": "Jane Smith",
  "checked_out_at": "2026-08-21T08:30:00Z",
  "due_at": "2026-09-05T18:00:00Z",
  "returned_at": null,
  "condition_note": ""
}
```

#### Enforced Business Rules:
- **Rule 1:** Asset must be `AVAILABLE` ($\rightarrow$ `409 Conflict` otherwise).
- **Rule 2:** Inactive employee cannot check out assets ($\rightarrow$ `400 Bad Request`).
- **Rule 3:** Employee cannot hold more than 3 open checkouts ($\rightarrow$ `409 Conflict`).
- **Rule 4:** `due_at` must be in the future and $\le 30$ days ahead ($\rightarrow$ `400 Bad Request`).
- **Rule 5:** Atomic database transaction guarantees no orphaned checkouts.
- **Rule 7:** Simultaneous concurrent checkouts serialize cleanly; exactly one wins (`201`), competitor receives `409 Conflict`.
- **Rule 8:** Unknown `asset_tag` or `employee_code` returns `404 Not Found`.

---

### 5. Return Asset
Enforces condition notes, maintenance status flags, and double-return conflict protection.
```bash
curl -X POST http://localhost:8000/api/v1/checkouts/8/return/ \
  -H "Authorization: Token 2879de74d786d2420a4dcb18b7a2d11673b22211" \
  -H "Content-Type: application/json" \
  -d '{
    "condition_note": "Returned in perfect condition",
    "needs_maintenance": false
  }'
```
**Response (`200 OK`):**
```json
{
  "id": 8,
  "asset": 2,
  "asset_tag": "LAP-002",
  "asset_name": "MacBook Pro 16 M3 Max",
  "employee": 3,
  "employee_code": "EMP-003",
  "employee_name": "Jane Smith",
  "checked_out_at": "2026-08-21T08:30:00Z",
  "due_at": "2026-09-05T18:00:00Z",
  "returned_at": "2026-08-21T08:32:15Z",
  "condition_note": "Returned in perfect condition"
}
```
*Note: If `needs_maintenance: true`, the asset status transitions to `MAINTENANCE`. Attempting to return an already returned checkout returns `409 Conflict` (Rule 6).*

---

### 6. Employee Checkout Summary (Single-Query ORM Aggregation)
Computes all 4 employee statistics in a **single database query using ORM aggregation** (no Python loops, no N+1 queries).
```bash
curl -X GET http://localhost:8000/api/v1/employees/EMP-001/summary/ \
  -H "Authorization: Token 2879de74d786d2420a4dcb18b7a2d11673b22211"
```
**Response (`200 OK`):**
```json
{
  "lifetime_checkouts": 2,
  "currently_held": 2,
  "currently_overdue": 1,
  "mean_hold_duration_days": 10.5
}
```

---

### 7. Overdue Checkouts Report
Query-optimized with `select_related` and sorted most overdue first (`due_at ASC`).
```bash
curl -X GET http://localhost:8000/api/v1/reports/overdue/ \
  -H "Authorization: Token 2879de74d786d2420a4dcb18b7a2d11673b22211"
```
**Response (`200 OK`):**
```json
{
  "count": 2,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 2,
      "asset_name": "Sony Alpha A7 IV Full-Frame",
      "asset_tag": "CAM-001",
      "employee_code": "EMP-002",
      "employee_name": "John Doe",
      "due_at": "2026-08-13T08:16:04Z",
      "days_overdue": 8
    },
    {
      "id": 1,
      "asset_name": "ThinkPad X1 Carbon Gen 11",
      "asset_tag": "LAP-001",
      "employee_code": "EMP-001",
      "employee_name": "Sarah Connor",
      "due_at": "2026-08-17T08:16:04Z",
      "days_overdue": 4
    }
  ]
}
```

---

## Periodic Background Processing (Celery & Celery Beat)

The service includes the periodic task `flag_overdue_checkouts`:
- **Execution Schedule:** Scheduled **hourly** via Celery Beat (`flag-overdue-checkouts-hourly`).
- **Behavior:** Scans for open overdue checkouts (`returned_at IS NULL AND due_at < NOW()`) and creates an `OverdueNotice` for today's date.
- **Idempotency Guarantee:** Enforced at the database level via `models.UniqueConstraint(fields=['checkout', 'notice_date'])` and `get_or_create`. Running the task repeatedly throughout the day never creates duplicate notices.

### Running Celery Manually:
```bash
# Start Celery Worker
celery -A config worker -l INFO -c 4

# Start Celery Beat Scheduler
celery -A config beat -l INFO
```

---

## Automated Test Suite

The test suite contains **45 comprehensive automated tests** with 100% pass rate covering models, concurrency, boundary dates, single-query aggregations, return flows, task idempotency, and health checks.

```bash
# Run full pytest suite
pytest
```

### Test Suite Summary:
```text
============================= test session starts =============================
platform win32 -- Python 3.14.2, pytest-9.1.1, pluggy-1.6.0
django: version: 5.2.17, settings: config.settings (from ini)
rootdir: D:\Volume D\field-asset-checkout-service
configfile: pytest.ini
plugins: django-4.14.0
collected 45 items

assets\tests\test_assets.py .......                                      [ 15%]
assets\tests\test_auth.py ..                                             [ 20%]
assets\tests\test_checkouts.py .........                                 [ 40%]
assets\tests\test_health.py ...                                          [ 46%]
assets\tests\test_models.py .........                                    [ 66%]
assets\tests\test_overdue.py ..                                          [ 71%]
assets\tests\test_returns.py .....                                       [ 82%]
assets\tests\test_summary.py ....                                        [ 91%]
assets\tests\test_tasks.py ..                                            [ 95%]
assets\tests\test_concurrency.py ..                                      [100%]

============================= 45 passed in 35.55s =============================
```

---

## Key Architectural & Engineering Decisions

### 1. Database-Level Concurrency & Deadlock Prevention
- Checkout requests acquire row-level locks via `select_for_update()` inside `transaction.atomic()`.
- To mathematically prevent deadlocks under high concurrency, locks are acquired in a **strict consistent order**:
  $$\text{Lock Order: } \text{Employee} \longrightarrow \text{Asset}$$
- This guarantees that two transactions competing for the same employee and asset will never enter an AB-BA deadlock cycle.

### 2. Single-Query ORM Aggregation for Employee Summary
- To comply with the requirement of computing all 4 employee summary metrics in a single query, we use Django ORM conditional aggregation (`Count` with filter `Q`, and `Avg` with `ExpressionWrapper` over `DurationField`):
  ```python
  Employee.objects.filter(employee_code=code).annotate(
      lifetime_checkouts=Count('checkouts', distinct=True),
      currently_held=Count('checkouts', filter=Q(checkouts__returned_at__isnull=True), distinct=True),
      currently_overdue=Count('checkouts', filter=Q(checkouts__returned_at__isnull=True, checkouts__due_at__lt=now), distinct=True),
      mean_duration=Avg(
          ExpressionWrapper(F('checkouts__returned_at') - F('checkouts__checked_out_at'), output_field=DurationField()),
          filter=Q(checkouts__returned_at__isnull=False)
      )
  )
  ```

---

## Assumptions

1. **Database Fallback for Local Development:** PostgreSQL 15 is configured as the primary production database (in Docker and `.env`), while SQLite is supported as a local development and pytest test runner fallback.
2. **Mean Duration Calculation:** If an employee has 0 returned checkouts, `mean_hold_duration_days` returns `null` (rather than 0.0) to accurately reflect the absence of historical hold data.
3. **Date Overdue Metric:** An asset where `due_at == now` is not yet overdue; `days_overdue` becomes $\ge 0$ only after `due_at < now`.
4. **Token Authentication:** DRF Token Authentication is used as the standard API authentication mechanism across all protected endpoints.

---

## Known Gaps

1. **Email Delivery Provider:** The Celery background task creates `OverdueNotice` database records; real email SMTP delivery (SES/SendGrid) is stubbed for testability in containerized environments.
2. **Screen Recording:** A placeholder link is provided above. Candidates record and insert their 6–8 minute walkthrough recording prior to final evaluation.

---

## Written Answers (`ANSWERS.md`)

Detailed technical answers for **Parts B, C, and D** are located at the repository root in [**`ANSWERS.md`**](ANSWERS.md):
- **Part B:** Diagnosis of 3 broken code snippets (N+1 queries, concurrency race conditions, non-idempotent Celery tasks).
- **Part C:** PostgreSQL 15 query optimization on a 4.2M row table with partial composite indexes and `EXPLAIN (ANALYZE, BUFFERS)` execution plans.
- **Part D:** Production reasoning on zero-downtime migrations (Expand/Contract pattern), 25s latency triage sequences, and GitHub Actions CI/CD deployment rollback strategies.
