# sample_repo — Test Fixture

A deliberately crafted Python repo used as input for reassure's integration tests.

Each file is designed to trigger specific analyzer outputs:

| File | Triggers |
|---|---|
| `src/auth/service.py` | Coverage: `reset_password` + `verify_session` uncovered. `login` has unit+integration, `logout` has unit only |
| `src/api/routes.py` | SOLID: god file (20+ functions, mixed concerns) |
| `src/db/queries.py` | Observability: entire dark module (zero logging/tracing) |
| `src/utils/legacy.py` | Dead code: all symbols unreferenced |
| `tests/unit/` | Classified as unit tests |
| `tests/integration/` | Classified as integration (sqlalchemy import) |
| `tests/e2e/` | Classified as e2e (playwright import) |

## Expected reassure output

```
Test Coverage
  AuthService.login          unit:2  integration:1  e2e:0   ✓
  AuthService.logout         unit:1  integration:0  e2e:0   ✓
  AuthService.reset_password unit:0  integration:0  e2e:0   ⚠ NO TESTS
  verify_session             unit:0  integration:0  e2e:0   ⚠ NO TESTS

Observability
  src/db/queries.py  ← entire module dark (0/4 functions instrumented)  ⚠

Dead Code
  utils/legacy.py::parse_v1_format    high confidence
  utils/legacy.py::convert_legacy_id  high confidence
  utils/legacy.py::LegacyClient       high confidence

SOLID Health
  src/api/routes.py  21 functions, mixed concerns  ⚠ GOD FILE
```
