# TDD Tests

Use this folder for test-driven development tests that may be red while a
feature is being designed or implemented.

Default verification still runs only the stable suite:

```bash
pytest
```

Run the TDD suite explicitly when working through a new behavior:

```bash
pytest tests_tdd
```

Guidelines:

- Keep tests focused on the behavior being designed.
- Move passing, durable regression tests into `tests/` when the behavior is
  implemented.
- Do not leave long-lived red tests here without a matching implementation task.
