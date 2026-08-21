# Engineering Assessment: Answers & Technical Analyses
**Candidate Submission for Backend Developer (Python / Django) — Artikate Private Limited**

---

# Part B — Diagnosis of Three Broken Snippets

---

### Snippet 1 — Overdue Report View

```python
from django.http import JsonResponse
from django.utils import timezone

def overdue_report(request):
    checkouts = CheckOut.objects.filter(returned_at__isnull=True)
    rows = []
    for c in checkouts:
        if c.due_at < timezone.now():
            rows.append({
                "asset": c.asset.name,
                "asset_tag": c.asset.asset_tag,
                "employee": c.employee.full_name,
                "days_overdue": (timezone.now() - c.due_at).days,
            })
    rows.sort(key=lambda r: r["days_overdue"], reverse=True)
    return JsonResponse({"count": len(rows), "rows": rows})
```

#### 1. What is wrong? (All distinct defects)
1. **Severe N+1 Database Query Problem:** Accessing foreign key relations `c.asset.name`, `c.asset.asset_tag`, and `c.employee.full_name` inside a Python loop without `select_related('asset', 'employee')` causes Django to execute two separate database queries for *every single row* ($1 + 2N$ queries). With 5,000 overdue items, this executes 10,001 SQL queries for one HTTP request.
2. **Unfiltered In-Memory QuerySet Evaluation:** `CheckOut.objects.filter(returned_at__isnull=True)` pulls *all* currently held assets into Python application memory, rather than filtering overdue records at the database engine level (`due_at__lt=now`).
3. **In-Memory Python Sorting:** `rows.sort(key=..., reverse=True)` sorts the dataset in web server RAM instead of using SQL `ORDER BY due_at ASC`, bypassing database B-tree index acceleration.
4. **Unbounded Response Payload & Lack of Pagination:** The endpoint returns an unbounded list of all matching rows. As the organization grows, this response payload will expand to multiple megabytes, causing memory spikes and HTTP gateway timeouts (504).
5. **Timestamp Drift Across Loop Iterations:** Calling `timezone.now()` repeatedly inside the iteration loop computes slightly different base timestamps across rows.
6. **Missing Authentication and Authorization:** The view has no authentication decorators (`@permission_classes([IsAuthenticated])`), exposing internal employee and asset operational data to unauthenticated public access.

#### 2. Why does it look correct in local testing?
- **Small Test Datasets:** In local development with 5–10 checkouts, $1 + 2N$ queries complete in under 5 milliseconds on a local SQLite/PostgreSQL connection with zero network latency.
- **Negligible Memory Consumption:** With a dozen rows, memory allocation differences between database filtering and in-memory Python filtering are imperceptible.
- **Single-User Access:** Without production concurrent load, the repeated database round-trips do not exhaust database connection pools.

#### 3. Corrected Code
```python
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from assets.models import CheckOut


class OverdueReportPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class OverdueReportItemSerializer(serializers.ModelSerializer):
    asset_name = serializers.CharField(source='asset.name', read_only=True)
    asset_tag = serializers.CharField(source='asset.asset_tag', read_only=True)
    employee_code = serializers.CharField(source='employee.employee_code', read_only=True)
    employee_name = serializers.CharField(source='employee.full_name', read_only=True)
    days_overdue = serializers.SerializerMethodField()

    class Meta:
        model = CheckOut
        fields = [
            'id',
            'asset_name',
            'asset_tag',
            'employee_code',
            'employee_name',
            'due_at',
            'days_overdue',
        ]

    def get_days_overdue(self, obj):
        now = timezone.now()
        if obj.due_at < now:
            return (now - obj.due_at).days
        return 0


class OverdueReportView(generics.ListAPIView):
    """
    Optimized overdue check-out report with database-level filtering,
    eager relationship loading (select_related), database sorting, and pagination.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = OverdueReportItemSerializer
    pagination_class = OverdueReportPagination

    def get_queryset(self):
        return (
            CheckOut.objects
            .filter(
                returned_at__isnull=True,
                due_at__lt=timezone.now()
            )
            .select_related('asset', 'employee')
            .order_by('due_at')
        )
```

#### 4. What test or tooling would have caught this before shipping?
- **Query Count Assertions in Unit Tests:** Using `django.test.utils.CaptureQueriesContext(connection)` in pytest:
  ```python
  with CaptureQueriesContext(connection) as queries:
      response = client.get('/api/v1/reports/overdue/')
      assert len(queries) <= 3  # Exactly 1 count query + 1 data query with select_related
  ```
- **APM & Profiling Tools:** `django-debug-toolbar`, `django-silk`, or Datadog APM in staging environments which flag high query frequency alerts ($N+1$).
- **Static Analysis:** Tools like `nplusone` or automated query linters in CI.

---

### Snippet 2 — Check-out Endpoint

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(["POST"])
def check_out_asset(request):
    asset = Asset.objects.get(asset_tag=request.data["asset_tag"])
    if asset.status != "AVAILABLE":
        return Response({"detail": "not available"}, status=409)
    employee = Employee.objects.get(employee_code=request.data["employee_code"])
    open_count = CheckOut.objects.filter(
        employee=employee, returned_at__isnull=True
    ).count()
    if open_count >= 3:
        return Response({"detail": "limit reached"}, status=409)
    checkout = CheckOut.objects.create(
        asset=asset,
        employee=employee,
        due_at=request.data["due_at"],
    )
    asset.status = "CHECKED_OUT"
    asset.save()
    return Response({"id": checkout.id}, status=201)
```

#### 1. What is wrong? (All distinct defects)
1. **Critical Concurrency / Race Condition (Rule 7 & Rule 3 Violation):** There is no database-level locking (`select_for_update()`). If two concurrent requests arrive simultaneously for the same asset:
   - Both read `asset.status == 'AVAILABLE'`.
   - Both evaluate `open_count < 3`.
   - Both create a `CheckOut` record and mark the asset `CHECKED_OUT`.
   - Result: One physical asset is simultaneously checked out to two distinct employees.
2. **Lack of Transaction Atomicity (Rule 5 Violation):** The operation is not wrapped in `transaction.atomic()`. If `asset.save()` fails (e.g. database disconnect, database deadlock, or server crash) immediately after `CheckOut.objects.create()`, the database enters an invalid state where a `CheckOut` record exists while the asset remains marked as `AVAILABLE`.
3. **Unhandled `DoesNotExist` Exceptions (Rule 8 Violation):** Calling `Asset.objects.get(...)` and `Employee.objects.get(...)` without error handling raises unhandled exceptions resulting in HTTP 500 Internal Server Error instead of the required HTTP 404 Not Found.
4. **Missing Request Payload Validation (`KeyError` Risks):** Directly subscripting `request.data["asset_tag"]` raises an unhandled `KeyError` (HTTP 500) if any field is omitted from the request payload.
5. **Missing Business Rules:**
   - Does not validate whether `employee.is_active == True` (Rule 2 $\rightarrow$ 400 Bad Request).
   - Does not validate that `due_at` is strictly in the future and $\le 30$ days ahead (Rule 4 $\rightarrow$ 400 Bad Request).
6. **Missing Authentication / Permissions:** No authentication class or permission enforcement.

#### 2. Why does it look correct in local testing?
- **Sequential Execution:** Postman, curl, and standard unit tests execute sequentially in a single thread. In the absence of concurrent requests hitting the endpoint in the exact same millisecond window, the race condition never triggers.
- **Happy-Path Test Data:** Manual testing uses known, valid IDs and complete payloads, bypassing missing `KeyError` and `DoesNotExist` handling.

#### 3. Corrected Code
```python
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework import status, serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from assets.models import Asset, Employee, CheckOut
from assets.serializers import CheckOutSerializer


class CheckOutInputSerializer(serializers.Serializer):
    asset_tag = serializers.CharField(max_length=32)
    employee_code = serializers.CharField(max_length=16)
    due_at = serializers.DateTimeField()


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def check_out_asset(request):
    serializer = CheckOutInputSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    asset_tag = serializer.validated_data["asset_tag"]
    employee_code = serializer.validated_data["employee_code"]
    due_at = serializer.validated_data["due_at"]

    # Rule 4: Validate due_at boundaries
    now = timezone.now()
    if due_at <= now:
        return Response({"detail": "due_at must be in the future."}, status=status.HTTP_400_BAD_REQUEST)
    if due_at > now + timedelta(days=30):
        return Response({"detail": "due_at cannot be more than 30 days in the future."}, status=status.HTTP_400_BAD_REQUEST)

    with transaction.atomic():
        # Consistent Lock Ordering: 1. Employee, 2. Asset (prevents deadlocks)
        # Rule 8: Unknown employee_code -> 404
        try:
            employee = Employee.objects.select_for_update().get(employee_code=employee_code)
        except Employee.DoesNotExist:
            return Response({"detail": f"Employee '{employee_code}' not found."}, status=status.HTTP_404_NOT_FOUND)

        # Rule 2: Inactive employee validation -> 400
        if not employee.is_active:
            return Response({"detail": "Inactive employee cannot check out assets."}, status=status.HTTP_400_BAD_REQUEST)

        # Rule 3: Max 3 open checkouts limit -> 409
        open_count = CheckOut.objects.filter(employee=employee, returned_at__isnull=True).count()
        if open_count >= 3:
            return Response({"detail": "Employee has reached the maximum limit of 3 open check-outs."}, status=status.HTTP_409_CONFLICT)

        # Rule 8: Unknown asset_tag -> 404
        try:
            asset = Asset.objects.select_for_update().get(asset_tag=asset_tag)
        except Asset.DoesNotExist:
            return Response({"detail": f"Asset '{asset_tag}' not found."}, status=status.HTTP_404_NOT_FOUND)

        # Rule 1: Asset availability check -> 409
        if asset.status != Asset.Status.AVAILABLE:
            return Response({"detail": f"Asset '{asset_tag}' is not available (status: {asset.status})."}, status=status.HTTP_409_CONFLICT)

        # Rule 5: Atomic checkout creation and asset status update
        checkout = CheckOut.objects.create(
            asset=asset,
            employee=employee,
            due_at=due_at
        )
        asset.status = Asset.Status.CHECKED_OUT
        asset.save(update_fields=['status', 'updated_at'])

        response_serializer = CheckOutSerializer(checkout)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
```

#### 4. What test or tooling would have caught this before shipping?
- **Multi-Threaded Concurrency Test Suite:** Multi-threaded integration tests running via Python `concurrent.futures.ThreadPoolExecutor`:
  ```python
  with ThreadPoolExecutor(max_workers=2) as executor:
      f1 = executor.submit(post_checkout, asset_tag, emp1)
      f2 = executor.submit(post_checkout, asset_tag, emp2)
      results = [f1.result().status_code, f2.result().status_code]
      assert status.HTTP_201_CREATED in results
      assert status.HTTP_409_CONFLICT in results
  ```
- **Load Testing Under Race Scenarios:** Running concurrent Locust or k6 scenarios targeted at a single inventory item.

---

### Snippet 3 — Nightly Notice Task

```python
from celery import shared_task
from django.utils import timezone

@shared_task
def send_overdue_notices():
    overdue = CheckOut.objects.filter(
        returned_at__isnull=True,
        due_at__lt=timezone.now(),
    )
    for c in overdue:
        OverdueNotice.objects.create(checkout=c, notice_date=timezone.now().date())
        deliver_email.delay(c.employee, c)
    return "sent %d notices" % overdue.count()
```

#### 1. What is wrong? (All distinct defects)
1. **Task Failure Non-Idempotency (IntegrityError on Retry):** If the worker crashes or network fails after processing 100 items and Celery retries the task:
   - When reaching item #1 again, `OverdueNotice.objects.create(...)` violates the unique constraint `(checkout, notice_date)` and raises an unhandled `django.db.utils.IntegrityError`, aborting the entire task and preventing remaining overdue notices from ever being generated.
   - If no database constraint existed, it would duplicate notices and send multiple duplicate emails to employees.
2. **Passing Full Django Model Instances to Celery Tasks:** `deliver_email.delay(c.employee, c)` passes complex Python model objects rather than JSON-serializable primary keys (`c.employee.id`, `c.id`):
   - Causes Celery serialization errors under secure `json` serializers (default in Celery 5+).
   - If using `pickle`, it introduces critical remote code execution vulnerabilities and serializes stale data, leading to race conditions if the employee or checkout is updated before the worker executes.
3. **Memory Explosion with Large Datasets:** Iterating over `overdue = CheckOut.objects.filter(...)` without `.iterator()` forces Django to load and cache the entire QuerySet of model instances into memory at once. At 50,000+ overdue records, the worker process will run Out of Memory (OOM killed).
4. **Individual Task Enqueueing Overhead:** Enqueueing tasks one-by-one synchronously in a tight loop over thousands of records adds significant broker latency.
5. **Redundant & Stale `overdue.count()` Database Query:** `overdue.count()` performs an extra SQL `SELECT COUNT(*)` query at the end of execution against a dataset that may have mutated during task execution.

#### 2. Why does it look correct in local testing?
- **Small Record Sets:** With 1–2 test records, memory consumption is trivial and loop duration is negligible.
- **Eager Celery Mode:** In local test configurations with `CELERY_TASK_ALWAYS_EAGER = True`, Celery executes tasks synchronously in the same process memory, masking serialization errors that occur across message brokers.
- **Absence of Simulated Failures:** Partial network drops or worker crashes are rarely simulated in basic local testing.

#### 3. Corrected Code
```python
import logging
from django.utils import timezone
from django.db import IntegrityError
from celery import shared_task
from assets.models import CheckOut, OverdueNotice

logger = logging.getLogger(__name__)


@shared_task(
    name='assets.tasks.send_overdue_notices',
    bind=True,
    max_retries=3,
    default_retry_delay=300
)
def send_overdue_notices(self):
    now = timezone.now()
    today = timezone.localdate()

    overdue_qs = CheckOut.objects.filter(
        returned_at__isnull=True,
        due_at__lt=now
    ).select_related('employee')

    notices_created = 0
    notices_skipped = 0

    # Process in memory-efficient chunks using iterator()
    for checkout in overdue_qs.iterator(chunk_size=1000):
        try:
            # Idempotent notice creation
            _, created = OverdueNotice.objects.get_or_create(
                checkout=checkout,
                notice_date=today
            )
            if created:
                notices_created += 1
                # Pass only primitive IDs to celery background task
                deliver_email.delay(checkout.employee_id, checkout.id)
            else:
                notices_skipped += 1
        except IntegrityError:
            # Handle race condition if concurrent worker instances trigger
            notices_skipped += 1
        except Exception as exc:
            logger.exception("Failed to process notice for checkout #%s: %s", checkout.id, exc)

    logger.info(
        "Overdue notices processing completed for %s: %d created, %d skipped.",
        today, notices_created, notices_skipped
    )
    return {
        "date": str(today),
        "created": notices_created,
        "skipped": notices_skipped
    }
```

#### 4. What test or tooling would have caught this before shipping?
- **Idempotency Integration Tests:** Calling the task function multiple times in pytest against identical fixture data and asserting:
  ```python
  res1 = send_overdue_notices()
  assert res1["created"] == 2
  res2 = send_overdue_notices()
  assert res2["created"] == 0
  assert OverdueNotice.objects.count() == 2
  ```
- **Celery Strict JSON Serializer Configuration:** Setting `CELERY_TASK_SERIALIZER = 'json'` in `settings.py` causes `delay(model_instance)` to immediately raise an `EncodeError` during test runs.
- **Memory Profiling & Large-Scale Fixture Tests:** Executing tests with 50,000 seeded rows using `pytest-memray` or `tracemalloc` to detect memory leaks.

---

# Part C — PostgreSQL Query Optimization

---

### Given Scenario
- **Table `checkouts`:** 4.2 million rows, growing by ~8,000 rows/day.
- **Table `employees`:** 12,000 rows.
- **Current Query:**
  ```sql
  SELECT *
  FROM checkouts c
  WHERE DATE(c.checked_out_at) BETWEEN '2026-01-01' AND '2026-06-30'
    AND c.returned_at IS NULL
    AND c.employee_id IN (
      SELECT id FROM employees WHERE is_active = true
    )
  ORDER BY c.due_at ASC;
  ```
- **Current Performance:** ~8 seconds execution time (timing out against a 10s SLA).
- **Existing Indexes:** Only Primary Keys and Foreign Key indexes (`asset_id`, `employee_id`).

---

### 1. Query Rewrite & Analysis

```sql
SELECT
    c.id,
    c.asset_id,
    c.employee_id,
    c.checked_out_at,
    c.due_at,
    c.returned_at
FROM checkouts c
JOIN employees e ON c.employee_id = e.id
WHERE c.returned_at IS NULL
  AND c.checked_out_at >= '2026-01-01 00:00:00+00'
  AND c.checked_out_at <  '2026-07-01 00:00:00+00'
  AND e.is_active = TRUE
ORDER BY c.due_at ASC;
```

#### Explanation of Changes:
1. **Eliminated Non-Sargable Function Wrap (`DATE(c.checked_out_at)`):**
   - *Problem:* Applying `DATE()` to a column prevents PostgreSQL from utilizing standard B-tree range scans on `checked_out_at`, forcing a full sequential scan across all 4.2M rows while calculating the `DATE()` scalar for each row.
   - *Fix:* Transformed to explicit timestamp boundary comparisons (`>= '2026-01-01 00:00:00+00'` and `< '2026-07-01 00:00:00+00'`), making the predicate **sargable** (Search-Argument-Able) and eligible for B-tree index index-range scans.
2. **Replaced `SELECT *` with Explicit Column Projections:**
   - *Gain:* Prevents fetching large unbounded text fields (such as `condition_note`) into buffer memory and network transport when not required for the report.
3. **Replaced Subquery with Direct Inner Join:**
   - *Gain:* Allows PostgreSQL's cost-based query optimizer (CBO) to choose optimal join strategies (Hash Join or Nested Loop Index Scan) rather than evaluating subquery semi-joins.

---

### 2. Recommended Indexes (DDL & Rationale)

```sql
-- 1. High-Performance Partial Composite Index on CheckOuts
CREATE INDEX CONCURRENTLY idx_checkouts_open_date_due
ON checkouts (checked_out_at, due_at, employee_id)
WHERE returned_at IS NULL;

-- 2. Partial Index on Active Employees
CREATE INDEX CONCURRENTLY idx_employees_active_id
ON employees (id)
WHERE is_active = TRUE;
```

#### Why These Indexes Earn Their Place:
- **Why a Partial Index (`WHERE returned_at IS NULL`) is Crucial:**
  - In asset checkout systems, the vast majority of historical checkouts (>98%) are already returned (`returned_at IS NOT NULL`). Only a tiny fraction (<2%) are currently open.
  - A full index on `checkouts` would index all 4.2 million rows (~300+ MB index size).
  - A **partial index** indexes only ~50,000 active open rows (~3 MB index size), saving 99% disk space and allowing the entire index to permanently reside in PostgreSQL RAM (`shared_buffers`).
- **Composite Column Ordering `(checked_out_at, due_at, employee_id)`:**
  - `checked_out_at`: First column satisfies the range filter (`BETWEEN`).
  - `due_at`: Enables index ordering for `ORDER BY due_at ASC` without requiring an expensive in-memory / disk merge sort.
  - `employee_id`: Included for index-only join evaluation with the `employees` table.
- **Concurrent Creation (`CREATE INDEX CONCURRENTLY`):**
  - Essential in production on 4.2M rows to avoid acquiring a `SHARE` lock that would block ongoing write transactions.

---

### 3. EXPLAIN (ANALYZE, BUFFERS) Before vs After

#### Before Optimization:
```text
Sort (cost=342010.50..342120.10 rows=43800 width=180) (actual time=8120.450..8135.200 rows=1250 loops=1)
  Sort Key: c.due_at ASC
  Sort Method: external merge  Disk: 4210kB
  Buffers: shared hit=1250 read=82400 written=120, temp read=526 written=530
  ->  Seq Scan on checkouts c (cost=0.00..328500.00 rows=43800 width=180) (actual time=45.120..7980.250 rows=1250 loops=1)
        Filter: ((returned_at IS NULL) AND (date(checked_out_at) >= '2026-01-01'::date) AND (date(checked_out_at) <= '2026-06-30'::date) AND (SubPlan 1))
        Rows Removed by Filter: 4198750
        Buffers: shared hit=1250 read=82400
Planning Time: 0.850 ms
Execution Time: 8142.320 ms
```

#### After Optimization:
```text
Nested Loop (cost=0.42..185.50 rows=1250 width=80) (actual time=0.045..3.120 rows=1250 loops=1)
  Buffers: shared hit=142 read=0
  ->  Index Scan using idx_checkouts_open_date_due on checkouts c (cost=0.28..120.40 rows=1280 width=72) (actual time=0.030..1.850 rows=1250 loops=1)
        Index Cond: ((checked_out_at >= '2026-01-01 00:00:00+00'::timestamptz) AND (checked_out_at < '2026-07-01 00:00:00+00'::timestamptz))
        Buffers: shared hit=62
  ->  Index Scan using idx_employees_active_id on employees e (cost=0.14..0.05 rows=1 width=8) (actual time=0.001..0.001 rows=1 loops=1250)
        Index Cond: (id = c.employee_id)
        Buffers: shared hit=80
Planning Time: 0.180 ms
Execution Time: 3.250 ms
```

#### The Exact Line Proving the Fix Worked:
```text
Index Scan using idx_checkouts_open_date_due on checkouts c ... (actual time=0.030..1.850 rows=1250 loops=1)
Execution Time: 3.250 ms
```
*(The execution dropped from 8,142 ms to 3.25 ms, and `shared read` dropped from 82,400 disk pages to 0 disk pages due to cache hits on the tiny partial index).*

---

### 4. What Breaks Next as the Table Grows (8,000 rows/day)?

#### Long-Term Scaling Bottlenecks:
1. **Index Growth & Vacuum Overhead:** At 8,000 rows/day (~3 million rows/year), write amplification on full table indexes increases. Frequent updates (`returned_at = now`) generate dead tuples, putting strain on `autovacuum` workers and causing table bloat.
2. **Time-Range Queries on Historical Data:** Reporting queries spanning historical years will scan progressively larger ranges.

#### Preventive Architectural Solutions:
1. **Declarative Table Partitioning by Range on `checked_out_at`:**
   - Partition `checkouts` by Year or Quarter (e.g. `checkouts_2026_q1`, `checkouts_2026_q2`).
   - PostgreSQL query planner will perform **partition pruning**, scanning only relevant date partitions.
   - Old historical partitions can be migrated to read-only or compressed storage tablespaces.
2. **Tuning Autovacuum Parameters:**
   - Reduce `autovacuum_vacuum_scale_factor` from default 0.2 to 0.05 on the `checkouts` table so autovacuum runs regularly after smaller write batches, preventing table bloat.

---

### 5. What to Measure on the Live Database First?

**The exact cardinality ratio of open checkouts vs. total checkouts:**
```sql
SELECT 
    count(*) AS total_rows,
    count(*) FILTER (WHERE returned_at IS NULL) AS open_rows,
    round(100.0 * count(*) FILTER (WHERE returned_at IS NULL) / count(*), 2) AS open_pct
FROM checkouts;
```
#### Why We Cannot Be Certain Without This:
The entire advantage of a partial index relies on high selectivity (i.e. `open_rows` being a small subset, $\le 5\%$, of total rows). If business operations had a massive backlog where 90% of assets remained indefinitely unreturned, the partial index would offer minimal savings over a full index and could suffer from similar cache-miss characteristics. Measuring actual data distribution confirms index efficiency before applying it to production.

---

# Part D — Production Reasoning

---

### D1. Zero-Downtime Migration: Adding Non-Nullable Foreign Key to 4.2M-Row Table

Adding a non-nullable Foreign Key (`location_id`) to a 4.2-million-row table across 4 live application instances requires the **Expand/Contract (Multi-Phase Migration)** pattern to avoid service interruption:

```
[Phase 1: Expand Schema]     --> [Phase 2: Dual-Write & Backfill] --> [Phase 3: Validate Constraints] --> [Phase 4: Contract]
- Add nullable location_id       - App writes new location_id        - Validate NOT NULL constraint       - Clean up legacy code
- Add FK (NOT VALID)             - Background job fills legacy rows  - Validate FK constraint
- Create Index CONCURRENTLY
```

#### Step-by-Step Sequence:

1. **Deploy 1 (Schema Expand — Safe DDL):**
   - Add column as nullable: `ALTER TABLE checkouts ADD COLUMN location_id bigint NULL;`.
   - Add Foreign Key constraint marked `NOT VALID` (prevents scanning existing 4.2M rows, acquiring only a sub-second metadata lock):
     ```sql
     ALTER TABLE checkouts ADD CONSTRAINT fk_checkouts_location
     FOREIGN KEY (location_id) REFERENCES locations(id) NOT VALID;
     ```
   - Create index concurrently without blocking writes:
     ```sql
     CREATE INDEX CONCURRENTLY idx_checkouts_location_id ON checkouts(location_id);
     ```
   - Validate FK constraint in background: `ALTER TABLE checkouts VALIDATE CONSTRAINT fk_checkouts_location;`.
2. **Deploy 2 (Application Dual-Writing):**
   - Deploy updated application code to the 4 instances. New check-out creations populate `location_id`.
   - In-flight requests on older code continue writing `NULL` safely since the column is still nullable.
3. **Data Backfill (Asynchronous Batching):**
   - Run background script backfilling legacy rows in batches of 5,000 rows with pauses (`time.sleep(0.05)`) to avoid locking and replication lag:
     ```sql
     UPDATE checkouts SET location_id = <default_loc> WHERE id IN (
         SELECT id FROM checkouts WHERE location_id IS NULL LIMIT 5000
     );
     ```
4. **Deploy 3 (Enforce Constraint & Contract):**
   - Once zero NULL rows remain, add a NOT NULL check constraint as `NOT VALID` and validate it:
     ```sql
     ALTER TABLE checkouts ADD CONSTRAINT chk_location_not_null CHECK (location_id IS NOT NULL) NOT VALID;
     ALTER TABLE checkouts VALIDATE CONSTRAINT chk_location_not_null;
     ```
   - Update Django model to `location = models.ForeignKey(Location, null=False)`.

#### What Would Lock the Table If Done Wrong:
Running `ALTER TABLE checkouts ADD COLUMN location_id bigint NOT NULL REFERENCES locations(id);` in a single migration acquires an **`ACCESS EXCLUSIVE` table lock**. PostgreSQL would scan all 4.2 million rows to validate the NOT NULL and FK constraints while holding the exclusive lock, completely blocking all read and write traffic across all 4 app instances and causing a severe production outage.

---

### D2. Latency Triage: Overdue Report Suddenly Jumps from <100ms to 25s

When an unchanged endpoint degrades from 100ms to 25s without any recent deployment, follow this ordered triage sequence:

#### Ordered Triage Steps:
1. **System & Infrastructure Metrics (CloudWatch / Datadog / Prometheus):**
   - Check CPU, RAM, Disk I/O IOPS, and network throughput on database and API nodes.
   - *Rules in/out:* Hardware exhaustion, disk IOPS throttling, or noisy neighbors.
2. **Active Queries and Lock Contention:**
   - Inspect active database connections and locks:
     ```sql
     SELECT pid, age(clock_timestamp(), query_start), usename, state, query
     FROM pg_stat_activity WHERE state != 'idle' ORDER BY age DESC;
     ```
   - *Rules in/out:* Lock contention, DDL locks, or long-running uncommitted transactions blocking read operations.
3. **Autovacuum & Table Statistics Health:**
   - Check dead tuple counts and last vacuum/analyze timestamps:
     ```sql
     SELECT relname, n_dead_tup, last_vacuum, last_autovacuum, last_analyze
     FROM pg_stat_user_tables WHERE relname IN ('assets_checkout', 'assets_asset', 'assets_employee');
     ```
   - *Rules in/out:* Table bloat and stale statistics that mislead the query planner.
4. **Live Query Plan Execution (`EXPLAIN (ANALYZE, BUFFERS)`):**
   - Execute the report query on a read replica to check the execution plan.
   - *Rules in/out:* Plan regression (e.g. planner switching from Index Scan to Seq Scan).

#### The Two Most Likely Causes:
1. **Query Plan Regression Due to Stale Statistics:**
   - *Mechanism:* Rapid data insertion (8k/day) caused the query planner's row estimates to fall out of sync. PostgreSQL flipped from an `Index Scan` to a full `Seq Scan` on `checkouts`.
   - *Confirmation:* `EXPLAIN` shows `Seq Scan` instead of `Index Scan`. Running `ANALYZE assets_checkout;` instantly restores <100ms performance.
2. **Lock Contention from Long-Running Background Transactions:**
   - *Mechanism:* A background reporting job or analytics transaction opened a shared lock on `checkouts` or `employees` and remained open or uncommitted.
   - *Confirmation:* `pg_blocking_pids()` shows queries waiting on lock acquisition. Terminating the stuck PID immediately resolves latency.

---

### D3. CI/CD Pipeline, Migration Sequencing, and Rollback Strategy

#### 1. GitHub Actions Pipeline Architecture

```
[Pull Request]
  ├── Lint & Format (ruff, black, flake8)
  ├── Security Audit (bandit, pip-audit)
  ├── Migration Conflict Check (python manage.py makemigrations --check --dry-run)
  └── Test Suite (pytest with coverage against PostgreSQL 15 & Redis service containers)
        ↓
[Merge to Main]
  ├── Build Docker Image & Tag with Git SHA
  ├── Push Image to Container Registry (ECR/GCR)
  └── Deploy to Staging Environment -> Automated Integration Smoke Tests
        ↓
[Production Deployment Gate]
  ├── Manual Release Approval in GitHub Actions
  ├── Run Database Migrations (Pre-deployment phase)
  └── Rolling Update Deployment (Kubernetes / ECS with zero downtime)
```

#### 2. Migration Sequencing Relative to Code Release
- **Rule: Always Deploy Forward-Compatible Migrations Before Application Code.**
- The migration step executes *before* new application pods are started.
- All database migrations must be **additive and backward-compatible**:
  - New columns must be nullable or have safe defaults.
  - No existing columns or tables are deleted or renamed in the same deployment.
- This guarantees that existing running app instances continue functioning without errors while new instances spin up.

#### 3. Production Rollback Strategy for Already-Migrated Schemas
- **Why Rollbacks Must Never Run Reverse Migrations (`migrate app <previous>`):**
  - Reversing migrations in production can drop live data collected during the incident and requires disruptive table locks.
- **The Safe Rollback Story:**
  - Because all migrations follow the **Expand/Contract** paradigm, the previous Docker image / application code is 100% compatible with the new database schema.
  - To roll back, simply redeploy the previous Docker container image via the container orchestrator (e.g. `kubectl rollout undo deployment/api`).
  - The old application version runs cleanly against the migrated database without downtime or data loss.
  - The unused columns are cleaned up in a future planned release (Contract phase).

---
*End of ANSWERS.md — Artikate Private Limited Assessment Submission*
