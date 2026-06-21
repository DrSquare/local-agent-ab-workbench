# PR and Release Workflow

This project is developed as small, reviewable feature branches. Keep every change offline-first, locally testable, and scoped to the module or post-MVP item being changed.

## Branch Workflow

1. Start from the latest local baseline for the work in progress.
2. Create a feature branch with the `codex/` prefix, for example `codex/module-10-openclaw-adapter`.
3. Implement the smallest complete behavior slice, including tests and docs.
4. Run one self-review pass before committing:
   - Check the diff for scope creep and accidental generated artifacts.
   - Confirm guardrails are enforced before any real adapter execution path.
   - Confirm config/schema changes reject unknown keys where applicable.
   - Confirm `sprint.md`, `PLAN.md`, and mirrored docs stay aligned.
5. Run the verification commands listed below.
6. Commit with a concise imperative message.
7. Push the branch and open a PR against the intended base branch.

## Required Verification

Run these before every PR:

```bash
py -3.13 -m ruff check .
py -3.13 -m pytest -q -p no:cacheprovider
py -3.13 -m agent_ab.cli validate-experiment experiments/demo_openclaw_prompt_ab.yaml
py -3.13 -m agent_ab.cli validate-experiment experiments/demo_openclaw_adapter.yaml
py -3.13 -m agent_ab.cli validate-taskpack taskpacks/openclaw_demo/tasks.yaml
py -3.13 -m agent_ab.cli metrics --category tool
```

Optional browser checks run automatically when Playwright and Chromium are installed:

```bash
py -3.13 -m pytest tests/test_post_mvp_browser_ui.py -q -p no:cacheprovider
```

## PR Checklist

Every PR should include:

- Summary of user-visible behavior or contract changes.
- Verification commands and results.
- Known skipped checks, with the reason.
- Risk notes for adapter execution, filesystem access, network access, and trace redaction.
- Screenshots only for visual UI changes that cannot be evaluated from tests.
- Updated `sprint.md` when the work completes or changes a tracked item.

## Review Guidance

Review in this order:

1. Contract correctness: schemas, validators, and output payloads.
2. Safety: path, command, endpoint, timeout, and opt-in execution gates.
3. Offline behavior: no cloud-only dependencies or external assets in the default path.
4. Tests: focused coverage for new behavior and regression risks.
5. Docs: commands, examples, and trackers match the implemented state.

## Release Workflow

Use this checklist for a tagged release:

1. Confirm all intended feature branches are merged.
2. Run the required verification commands from a clean checkout.
3. Run the local demo and export reports:

```bash
py -3.13 -m agent_ab.cli run-demo --output-root demo_output
py -3.13 -m agent_ab.cli export-runs demo_output/runs --output demo_output/reports/runs.csv --format csv
py -3.13 -m agent_ab.cli compare-runs demo_output/runs --output demo_output/reports/comparison.json
```

4. Review generated demo output manually, then remove local generated artifacts before tagging.
5. Update release notes with:
   - Implemented modules or post-MVP items.
   - Verification command results.
   - Known limitations and skipped optional checks.
   - Any explicit opt-in steps required for real adapter execution.
6. Tag with `vMAJOR.MINOR.PATCH` only after the working tree is clean.
7. Publish the GitHub release from the tag.

## Rollback Guidance

If a release needs to be rolled back, prefer reverting the specific merge commit or tag rather than rewriting history. Keep generated run artifacts out of rollback commits unless they are explicitly part of the release evidence.
