"""Offline seed generation for expert-authored taskpacks.

This module deliberately does not scrape Mercor or O*NET. It ships a small set
of public, source-attributed seeds and can turn them into normal TaskPack YAML
for later human review and scorer work.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator

from agent_ab.schemas.common import (
    IdentifierMixin,
    StrictBaseModel,
    _non_blank,
    _normalized_non_blank_list,
    is_identifier,
)
from agent_ab.schemas.task import (
    TaskCase,
    TaskPack,
    TaskValidator,
    TaskWorkspace,
    is_known_or_custom_validator_type,
    validate_relative_workspace_path,
)

MERCOR_APEX_LEADERBOARD_URL = "https://www.mercor.com/apex/apex-agents-leaderboard/"
MERCOR_APEX_DATASET_URL = "https://huggingface.co/datasets/Mercor/APEX-Agents"
ONET_RESOURCE_URL = "https://www.dol.gov/agencies/eta/onet"
ONET_TASK_STATEMENTS_URL = (
    "https://www.onetcenter.org/dl_files/database/db_30_3_text/Task%20Statements.txt"
)
ONET_WORK_ACTIVITY_URL = (
    "https://www.onetcenter.org/dl_files/database/db_30_3_text/"
    "GWAs%20to%20IWAs%20to%20DWAs.txt"
)
NBER_APPENDIX_A4_URL = "https://www.nber.org/system/files/working_papers/w34255/w34255.pdf"

_ONET_OCCUPATION_RE = re.compile(r"^\d{2}-\d{4}\.\d{2}$")
_ONET_ACTIVITY_RE = re.compile(r"^4\.A\.[A-Za-z0-9.]+$")


def _normalize_tags(values: list[str], field_name: str) -> list[str]:
    return _normalized_non_blank_list(values, field_name)


class OnetOccupationReference(StrictBaseModel):
    """O*NET occupation code and title used for seed metadata."""

    code: str = Field(..., description="Official O*NET-SOC occupation code.")
    title: str = Field(..., description="Official O*NET occupation title.")
    description: str = Field(..., description="O*NET occupation description.")
    source_url: str = Field(..., description="Source URL for the occupation profile.")

    @field_validator("code")
    @classmethod
    def code_is_onet_soc(cls, value: str) -> str:
        code = _non_blank(value, "O*NET occupation code")
        if not _ONET_OCCUPATION_RE.match(code):
            raise ValueError("O*NET occupation code must look like 13-2051.00")
        return code

    @field_validator("title", "description", "source_url")
    @classmethod
    def text_fields_not_blank(cls, value: str) -> str:
        return _non_blank(value, "O*NET occupation field")


class OnetTaskReference(StrictBaseModel):
    """O*NET task statement reference from the public Task Statements data file."""

    task_id: int = Field(..., ge=1, description="Official O*NET Task ID.")
    task_statement: str = Field(..., description="Official O*NET task statement.")
    task_type: str = Field(..., description="O*NET task type, such as Core or n/a.")
    date: str = Field(..., description="O*NET task statement update date.")
    domain_source: str = Field(..., description="O*NET task domain source.")
    source_url: str = Field(default=ONET_TASK_STATEMENTS_URL)

    @field_validator("task_statement", "task_type", "date", "domain_source", "source_url")
    @classmethod
    def text_fields_not_blank(cls, value: str) -> str:
        return _non_blank(value, "O*NET task field")


class OnetActivityClassification(StrictBaseModel):
    """NBER Appendix A.4-style IWA classification over O*NET work activities."""

    method: str = Field(default="nber_appendix_a4_iwa_prompt_mapping")
    evidence: str = Field(..., description="Short explanation for this seed-to-IWA mapping.")
    gwa_element_id: str = Field(..., description="O*NET General Work Activity element ID.")
    gwa_name: str = Field(..., description="O*NET General Work Activity name.")
    iwa_element_id: str = Field(..., description="O*NET Intermediate Work Activity element ID.")
    iwa_name: str = Field(..., description="O*NET Intermediate Work Activity statement.")
    dwa_element_id: str = Field(..., description="O*NET Detailed Work Activity element ID.")
    dwa_name: str = Field(..., description="O*NET Detailed Work Activity statement.")
    source_url: str = Field(default=ONET_WORK_ACTIVITY_URL)
    appendix_url: str = Field(default=NBER_APPENDIX_A4_URL)

    @field_validator("gwa_element_id", "iwa_element_id", "dwa_element_id")
    @classmethod
    def element_ids_are_work_activities(cls, value: str) -> str:
        element_id = _non_blank(value, "O*NET work activity element id")
        if not _ONET_ACTIVITY_RE.match(element_id):
            raise ValueError("O*NET work activity element IDs must start with 4.A.")
        return element_id

    @field_validator("method", "evidence", "gwa_name", "iwa_name", "dwa_name", "source_url", "appendix_url")
    @classmethod
    def text_fields_not_blank(cls, value: str) -> str:
        return _non_blank(value, "O*NET activity classification field")


class MercorApexMetadata(StrictBaseModel):
    """Public APEX-Agents metadata attached to a human expert seed."""

    benchmark: str = Field(default="APEX-Agents")
    job_category: str = Field(..., description="Mercor public job category.")
    expert_role: str = Field(..., description="Role used to author or frame the seed.")
    visible_metadata: dict[str, Any] = Field(default_factory=dict)
    source_url: str = Field(default=MERCOR_APEX_LEADERBOARD_URL)
    dataset_url: str = Field(default=MERCOR_APEX_DATASET_URL)
    source_limitations: list[str] = Field(
        default_factory=lambda: [
            "Built from public leaderboard/sample-task facts only.",
            "Full APEX-Agents dataset is gated and is not crawled by this module.",
            "Generated tasks require human review before benchmark use.",
        ]
    )

    @field_validator("benchmark", "job_category", "expert_role", "source_url", "dataset_url")
    @classmethod
    def text_fields_not_blank(cls, value: str) -> str:
        return _non_blank(value, "Mercor metadata field")

    @field_validator("source_limitations")
    @classmethod
    def limitations_not_blank(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value, "source limitation")


class HumanExpertTaskSeed(IdentifierMixin):
    """One source-attributed expert seed query plus taxonomy metadata."""

    role: str = Field(..., description="Human expert role represented by the seed.")
    query: str = Field(..., min_length=1, description="Task query generated from the seed.")
    mercor: MercorApexMetadata
    occupation: OnetOccupationReference
    onet_task: OnetTaskReference
    onet_activity: OnetActivityClassification
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role", "query")
    @classmethod
    def text_fields_not_blank(cls, value: str) -> str:
        return _non_blank(value, "human expert seed field")

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value, "seed tag")


class SeedTaskGenerationConfig(StrictBaseModel):
    """Config for deterministic seed-to-TaskPack generation."""

    taskpack_id: str = Field(default="mercor_apex_expert_seeded")
    taskpack_version: int = Field(default=1, ge=1)
    description: str | None = Field(
        default="Mercor APEX-inspired expert seed tasks with O*NET metadata tags."
    )
    seeds: list[HumanExpertTaskSeed] = Field(..., min_length=1)
    variants_per_seed: int = Field(default=1, ge=1, le=5)
    workspace_fixture: str = Field(default="workspaces/expert_seed")
    validator_type: str = Field(default="custom.human_expert_rubric")
    tags: list[str] = Field(
        default_factory=lambda: [
            "source:mercor-apex-public",
            "taxonomy:onet",
            "classification:nber-appendix-a4",
        ]
    )
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("taskpack_id")
    @classmethod
    def taskpack_id_is_identifier(cls, value: str) -> str:
        taskpack_id = _non_blank(value, "taskpack id")
        if not is_identifier(taskpack_id):
            raise ValueError(
                "taskpack_id must start with a letter and contain only letters, "
                "numbers, dash, dot, or underscore"
            )
        return taskpack_id

    @field_validator("workspace_fixture")
    @classmethod
    def fixture_is_relative(cls, value: str) -> str:
        return validate_relative_workspace_path(value, "workspace fixture")

    @field_validator("validator_type")
    @classmethod
    def validator_type_is_supported(cls, value: str) -> str:
        validator_type = _non_blank(value, "validator type")
        if not is_known_or_custom_validator_type(validator_type):
            raise ValueError("validator_type must be built-in or custom.<name>")
        return validator_type

    @field_validator("tags")
    @classmethod
    def tags_not_blank_or_duplicate(cls, value: list[str]) -> list[str]:
        return _normalize_tags(value, "taskpack tag")

    @model_validator(mode="after")
    def seed_ids_are_unique(self) -> SeedTaskGenerationConfig:
        seed_ids = [seed.id for seed in self.seeds]
        duplicates = sorted({seed_id for seed_id in seed_ids if seed_ids.count(seed_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate seed ids: {duplicates}")
        return self


def mercor_apex_public_seeds() -> list[HumanExpertTaskSeed]:
    """Return the built-in public seed set derived from APEX-Agents examples."""

    return [
        HumanExpertTaskSeed(
            id="investment_banking_merger_model",
            role="Investment Banking Analyst",
            query=(
                "Review the provided merger-model workbook, calculate accretion or dilution "
                "under the requested sensitivities, and return rounded percentage impacts with "
                "the key assumptions used."
            ),
            mercor=MercorApexMetadata(
                job_category="Investment Banking Analyst",
                expert_role="Investment banking analyst",
                visible_metadata={
                    "public_role_description": (
                        "Builds financial models, values companies, and prepares pitch materials."
                    ),
                    "example_employers": [
                        "Goldman Sachs",
                        "Morgan Stanley",
                        "JPMorgan",
                        "Barclays",
                    ],
                    "expected_output": "spreadsheet/numeric analysis",
                    "workflow_tags": [
                        "financial-modeling",
                        "valuation",
                        "merger-analysis",
                    ],
                },
            ),
            occupation=OnetOccupationReference(
                code="13-2051.00",
                title="Financial and Investment Analysts",
                description=(
                    "Conduct quantitative analyses of investment programs or financial data, "
                    "including valuation of businesses."
                ),
                source_url="https://www.onetonline.org/link/summary/13-2051.00",
            ),
            onet_task=OnetTaskReference(
                task_id=21590,
                task_statement=(
                    "Employ financial models to develop solutions to financial problems or "
                    "to assess the financial or capital impact of transactions."
                ),
                task_type="n/a",
                date="11/2020",
                domain_source="Analyst",
            ),
            onet_activity=OnetActivityClassification(
                evidence=(
                    "The query asks for spreadsheet sensitivity analysis and transaction impact "
                    "calculations using a merger model."
                ),
                gwa_element_id="4.A.2.a.4",
                gwa_name="Analyzing Data or Information",
                iwa_element_id="4.A.2.a.4.k",
                iwa_name="Analyze business or financial data.",
                dwa_element_id="4.A.2.a.4.k.3",
                dwa_name="Apply mathematical models of financial or business conditions.",
            ),
            tags=[
                "role:investment-banking-analyst",
                "domain:finance",
                "output:spreadsheet",
                "onet:13-2051.00",
                "onet-task:21590",
                "iwa:4.A.2.a.4.k",
            ],
        ),
        HumanExpertTaskSeed(
            id="management_consulting_market_score",
            role="Management Consultant",
            query=(
                "Analyze category consumption data, compute a weighted market-penetration "
                "score, and summarize the commercial implications for a client recommendation."
            ),
            mercor=MercorApexMetadata(
                job_category="Management Consultant",
                expert_role="Management consultant",
                visible_metadata={
                    "public_role_description": (
                        "Analyzes industries, evaluates markets, and builds strategic or financial models."
                    ),
                    "example_employers": [
                        "McKinsey",
                        "BCG",
                        "Deloitte",
                        "Accenture",
                        "EY",
                    ],
                    "expected_output": "business analysis with numeric score",
                    "workflow_tags": [
                        "market-analysis",
                        "commercial-diligence",
                        "strategy",
                    ],
                },
            ),
            occupation=OnetOccupationReference(
                code="13-1111.00",
                title="Management Analysts",
                description=(
                    "Conduct organizational studies and evaluations to assist management in "
                    "operating more efficiently and effectively."
                ),
                source_url="https://www.onetonline.org/link/summary/13-1111.00",
            ),
            onet_task=OnetTaskReference(
                task_id=7277,
                task_statement=(
                    "Analyze data gathered and develop solutions or alternative methods of proceeding."
                ),
                task_type="Core",
                date="08/2022",
                domain_source="Occupational Expert",
            ),
            onet_activity=OnetActivityClassification(
                evidence=(
                    "The query asks for quantitative market data analysis followed by a client-facing "
                    "recommendation."
                ),
                gwa_element_id="4.A.2.a.4",
                gwa_name="Analyzing Data or Information",
                iwa_element_id="4.A.2.a.4.g",
                iwa_name="Analyze data to improve operations.",
                dwa_element_id="4.A.2.a.4.g.14",
                dwa_name="Analyze data to identify or resolve operational problems.",
            ),
            tags=[
                "role:management-consultant",
                "domain:strategy",
                "output:analysis",
                "onet:13-1111.00",
                "onet-task:7277",
                "iwa:4.A.2.a.4.g",
            ],
        ),
        HumanExpertTaskSeed(
            id="corporate_law_lease_review",
            role="Corporate Lawyer",
            query=(
                "Review the lease excerpts and answer whether the tenant may install new flooring; "
                "provide a yes/no conclusion with concise contractual reasoning."
            ),
            mercor=MercorApexMetadata(
                job_category="Corporate Lawyer",
                expert_role="Corporate lawyer",
                visible_metadata={
                    "public_role_description": (
                        "Drafts and reviews contracts, performs legal research, and handles "
                        "regulatory or transactional matters."
                    ),
                    "example_employers": [
                        "Latham & Watkins",
                        "Skadden",
                        "Cravath",
                    ],
                    "expected_output": "legal conclusion with explanation",
                    "workflow_tags": [
                        "contract-review",
                        "legal-research",
                        "transactional-law",
                    ],
                },
            ),
            occupation=OnetOccupationReference(
                code="23-1011.00",
                title="Lawyers",
                description=(
                    "Represent clients in legal matters and advise them on legal rights and obligations."
                ),
                source_url="https://www.onetonline.org/link/summary/23-1011.00",
            ),
            onet_task=OnetTaskReference(
                task_id=20877,
                task_statement=(
                    "Prepare, draft, and review legal documents, such as wills, deeds, "
                    "patent applications, mortgages, leases, and contracts."
                ),
                task_type="Core",
                date="08/2024",
                domain_source="Incumbent",
            ),
            onet_activity=OnetActivityClassification(
                evidence=(
                    "The query asks for lease interpretation and a legal conclusion grounded in "
                    "contract language."
                ),
                gwa_element_id="4.A.2.a.4",
                gwa_name="Analyzing Data or Information",
                iwa_element_id="4.A.2.a.4.h",
                iwa_name="Research laws, precedents, or other legal data.",
                dwa_element_id="4.A.2.a.4.h.1",
                dwa_name="Identify implications for cases from legal precedents or other legal information.",
            ),
            tags=[
                "role:corporate-lawyer",
                "domain:law",
                "output:legal-analysis",
                "onet:23-1011.00",
                "onet-task:20877",
                "iwa:4.A.2.a.4.h",
            ],
        ),
    ]


def default_seed_generation_config() -> SeedTaskGenerationConfig:
    """Build the default public-seed generation config."""

    return SeedTaskGenerationConfig(seeds=mercor_apex_public_seeds())


def generate_seed_taskpack(config: SeedTaskGenerationConfig | None = None) -> TaskPack:
    """Generate a TaskPack from human expert seeds.

    The generated tasks are deterministic and declarative. They intentionally use
    a custom rubric validator because expert-work tasks need later human or
    model-assisted scoring, not Module 2 file validators.
    """

    generation_config = config or default_seed_generation_config()
    tasks: list[TaskCase] = []
    for seed in generation_config.seeds:
        for variant_index in range(1, generation_config.variants_per_seed + 1):
            task_id = seed.id
            query = seed.query
            variant_metadata: dict[str, Any] = {}
            if generation_config.variants_per_seed > 1:
                task_id = f"{seed.id}.seed_{variant_index}"
                variant_metadata["variant_index"] = variant_index
                if variant_index > 1:
                    query = (
                        f"{seed.query}\n\n"
                        f"Seed variation {variant_index}: explicitly cite the O*NET task "
                        f"statement {seed.onet_task.task_id} when explaining the approach."
                    )

            task = TaskCase(
                id=task_id,
                description=f"{seed.role} seed generated from public APEX/O*NET metadata.",
                query=query,
                workspace=TaskWorkspace(fixture=generation_config.workspace_fixture),
                validators=[
                    TaskValidator(
                        type=generation_config.validator_type,
                        description="Expert rubric placeholder for role-specific grading.",
                        metadata={
                            "seed_id": seed.id,
                            "role": seed.role,
                            "expected_review": (
                                "Score correctness, completeness, use of provided artifacts, "
                                "and alignment with expert-domain conventions."
                            ),
                            "requires_human_or_model_judge": True,
                        },
                    )
                ],
                tags=[*generation_config.tags, *seed.tags],
                metadata={
                    **variant_metadata,
                    "generation": {
                        "strategy": "deterministic_seed_expansion",
                        "source_seed_id": seed.id,
                        "source_limitations": seed.mercor.source_limitations,
                    },
                    "mercor": seed.mercor.model_dump(mode="json"),
                    "onet": {
                        "occupation": seed.occupation.model_dump(mode="json"),
                        "task": seed.onet_task.model_dump(mode="json"),
                        "activity_classification": seed.onet_activity.model_dump(mode="json"),
                    },
                    "seed_metadata": seed.metadata,
                },
            )
            tasks.append(task)

    return TaskPack(
        id=generation_config.taskpack_id,
        version=generation_config.taskpack_version,
        description=generation_config.description,
        tasks=tasks,
        tags=generation_config.tags,
        metadata={
            "generator": "agent_ab.task_seed_generation",
            "source_urls": [
                MERCOR_APEX_LEADERBOARD_URL,
                MERCOR_APEX_DATASET_URL,
                ONET_RESOURCE_URL,
                ONET_TASK_STATEMENTS_URL,
                ONET_WORK_ACTIVITY_URL,
                NBER_APPENDIX_A4_URL,
            ],
            "notes": [
                "No live source crawling is performed.",
                "Public seeds should be replaced or extended with licensed exports when available.",
                "O*NET IWA mappings follow the Appendix A.4 classification shape and require review.",
            ],
            **generation_config.metadata,
        },
    )


def write_seed_taskpack(
    output_path: str | Path,
    config: SeedTaskGenerationConfig | None = None,
) -> TaskPack:
    """Generate and write a seed TaskPack plus its shared fixture directory."""

    generation_config = config or default_seed_generation_config()
    taskpack = generate_seed_taskpack(generation_config)
    output = Path(output_path)
    taskpack.to_yaml_file(output)
    workspace_path = output.parent / generation_config.workspace_fixture
    workspace_path.mkdir(parents=True, exist_ok=True)
    readme = workspace_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# Expert Seed Workspace",
                "",
                "This fixture is intentionally minimal.",
                "",
                "Generated APEX/O*NET seed tasks need licensed task artifacts,",
                "gold outputs, or human-expert rubrics before real benchmark use.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return taskpack
