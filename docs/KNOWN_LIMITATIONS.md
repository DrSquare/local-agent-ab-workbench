# Known Limitations

- Real OpenClaw CLI execution is not enabled by default. Module 10 prepares command plans, and Module 11 validates guardrails before future execution paths use them.
- The deterministic mock adapter only satisfies filesystem validators; it does not model real desktop, browser, shell, or LLM behavior.
- Reporting currently summarizes local run trace artifacts. It does not compute aggregate statistical significance across repeated A/B runs yet.
- Secret redaction is pattern-based and conservative; adapter-specific redaction rules may be needed as real traces become richer.
- The frontend is intentionally no-build static HTML/CSS/JS. Larger UI needs may justify a bundled frontend toolchain later.
