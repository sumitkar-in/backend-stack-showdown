# Shared API Contract Test Checklist

Run against every implementation without changing tests. Keep fixture IDs derived from verified seed rows.

1. GET `/health` -> 200, exact `{"status":"ok"}`; no DB query.
2. GET `/readings/1` -> 200; `id=1`; expected field names/types; Asia/Kolkata three-decimal timestamp (`+05:30`).
3. GET `/readings/1000000` -> 200; last seeded row exists.
4. GET `/readings/1000001` before writes -> 404, `{ "error": "not_found" }`.
5. GET `/readings?deviceId=17&from=2026-01-01T00:00:00.000%2B05:30&to=2026-01-13T00:00:00.000%2B05:30&limit=50&offset=0` -> 50 items descending observedAt/id.
6. Same GET with `offset=50` -> next page with no overlap.
7. Device without readings -> empty list and identical pagination envelope.
8. GET `/readings/stats` for device 17 full seed range -> `count=1000`; sums/min/max match SQL exactly.
9. Stats for an empty time window -> count/sums 0, min/max null.
10. POST `/readings` valid -> 201, new ID, normalized timestamp; GET by ID returns identical content.
11. POST `/readings/batch` with 10 valid records -> 201 `{"inserted":10}`; DB count increases 10.
12. Batch with one bad record -> 422; **no** partial insert.
13. POST malformed JSON -> 400 and canonical error shape.
14. POST missing `temperatureCenti` -> 422.
15. POST invalid integer types, including float for integer fields -> 422.
16. POST unknown device ID -> 422, canonical error shape.
17. GET readings with bad `deviceId`, invalid RFC3339 or `from >= to` -> 422.
18. GET readings with `limit=101`, `offset=-1` -> 422.
19. GET negative/noninteger ID -> 422.
20. Load test smoke: 10 VUs, 10s, no contract errors before 100-VU run.

**Important:** each test that inserts data must use a transaction-compatible disposable database / baseline restore or deterministic cleanup. Never pollute the 1M publication-grade snapshot.
