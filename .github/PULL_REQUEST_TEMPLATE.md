## Summary

- 

## Verification

- [ ] `py -3.13 -m ruff check .`
- [ ] `py -3.13 -m pytest -q -p no:cacheprovider`
- [ ] `py -3.13 -m agent_ab.cli validate-experiment experiments/demo_openclaw_prompt_ab.yaml`
- [ ] `py -3.13 -m agent_ab.cli validate-experiment experiments/demo_openclaw_adapter.yaml`
- [ ] `py -3.13 -m agent_ab.cli validate-taskpack taskpacks/openclaw_demo/tasks.yaml`
- [ ] `py -3.13 -m agent_ab.cli metrics --category tool`

## Risk Review

- [ ] Filesystem/path policy impact reviewed
- [ ] Command execution impact reviewed
- [ ] Network/offline behavior reviewed
- [ ] Trace redaction impact reviewed
- [ ] Optional browser/UI checks noted when relevant

## Notes

- 
