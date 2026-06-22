from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from agent_ab.cli import app
from agent_ab.config import validate_taskpack_with_fixtures
from agent_ab.task_seed_generation import (
    OnetOccupationReference,
    SeedTaskGenerationConfig,
    generate_seed_taskpack,
    mercor_apex_public_seeds,
    write_seed_taskpack,
)


def test_public_mercor_seeds_include_onet_and_nber_metadata() -> None:
    seeds = mercor_apex_public_seeds()

    assert [seed.id for seed in seeds] == [
        "investment_banking_merger_model",
        "management_consulting_market_score",
        "corporate_law_lease_review",
    ]

    investment_seed = seeds[0]
    assert investment_seed.mercor.job_category == "Investment Banking Analyst"
    assert investment_seed.occupation.code == "13-2051.00"
    assert investment_seed.onet_task.task_id == 21590
    assert investment_seed.onet_activity.iwa_element_id == "4.A.2.a.4.k"
    assert investment_seed.onet_activity.appendix_url.endswith("w34255.pdf")
    assert "Full APEX-Agents dataset is gated" in investment_seed.mercor.source_limitations[1]


def test_seed_metadata_models_reject_unknown_keys_and_bad_codes() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        OnetOccupationReference.model_validate(
            {
                "code": "13-2051.00",
                "title": "Financial and Investment Analysts",
                "description": "Analyze financial data.",
                "source_url": "https://www.onetonline.org/link/summary/13-2051.00",
                "unexpected": True,
            }
        )

    with pytest.raises(ValidationError, match="must look like"):
        OnetOccupationReference(
            code="financial-analyst",
            title="Financial and Investment Analysts",
            description="Analyze financial data.",
            source_url="https://www.onetonline.org/link/summary/13-2051.00",
        )


def test_generation_config_rejects_duplicate_seeds_and_bad_validator_type() -> None:
    seed = mercor_apex_public_seeds()[0]

    with pytest.raises(ValidationError, match="duplicate seed ids"):
        SeedTaskGenerationConfig(seeds=[seed, seed])

    with pytest.raises(ValidationError, match="validator_type"):
        SeedTaskGenerationConfig(seeds=[seed], validator_type="human_rubric")


def test_generate_seed_taskpack_is_taskpack_compatible() -> None:
    taskpack = generate_seed_taskpack()

    assert taskpack.id == "mercor_apex_expert_seeded"
    assert len(taskpack.tasks) == 3
    assert taskpack.tags == [
        "source:mercor-apex-public",
        "taxonomy:onet",
        "classification:nber-appendix-a4",
    ]

    banking_task = taskpack.tasks[0]
    assert banking_task.validators[0].type == "custom.human_expert_rubric"
    assert banking_task.metadata["mercor"]["job_category"] == "Investment Banking Analyst"
    assert banking_task.metadata["onet"]["task"]["task_id"] == 21590
    assert banking_task.metadata["onet"]["activity_classification"]["dwa_element_id"] == "4.A.2.a.4.k.3"
    assert "onet-task:21590" in banking_task.tags


def test_write_seed_taskpack_creates_fixture_and_validates(tmp_path: Path) -> None:
    output = tmp_path / "seed_pack" / "tasks.yaml"

    written = write_seed_taskpack(output)
    validated = validate_taskpack_with_fixtures(output)

    assert written.id == validated.id
    assert (tmp_path / "seed_pack" / "workspaces" / "expert_seed" / "README.md").is_file()
    assert [task.id for task in validated.tasks] == [
        "investment_banking_merger_model",
        "management_consulting_market_score",
        "corporate_law_lease_review",
    ]


def test_generate_seed_taskpack_cli_writes_yaml_and_fixture(tmp_path: Path) -> None:
    runner = CliRunner()
    output = tmp_path / "cli_seed_pack" / "tasks.yaml"

    result = runner.invoke(
        app,
        [
            "generate-seed-taskpack",
            "--output",
            str(output),
            "--taskpack-id",
            "cli_seed_pack",
            "--variants-per-seed",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    validated = validate_taskpack_with_fixtures(output)
    assert validated.id == "cli_seed_pack"
    assert len(validated.tasks) == 6
    assert validated.tasks[0].id == "investment_banking_merger_model.seed_1"
    assert "Seed variation 2" in validated.tasks[1].query
