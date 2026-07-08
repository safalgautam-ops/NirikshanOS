"""Analysis planner: converts a flat list of selected modules into a
structured execution plan (a list of AnalysisJobPlan objects).

Each AnalysisJobPlan maps to exactly one future job row in analysis_jobs.
The grouping rules are:

  - Batchable modules that share the same (batch_group, queue_name,
    runtime_image, isolation_level) → one job, all modules run inside
    one container invocation.
  - Non-batchable modules → one job each, always.

The planner produces no side effects and touches no database. It is a
pure function over the module list: policy.py runs before it (ensures
the caller is allowed), job_service.py runs after it (persists the plan
into analysis_jobs + analysis_tasks rows).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.features.analysis.module_registry import (
    AnalysisModule,
    IsolationLevel,
    QueueName,
)


@dataclass(frozen=True)
class AnalysisJobPlan:
    modules:         list[AnalysisModule]
    queue_name:      QueueName
    runtime_image:   str
    isolation_level: IsolationLevel
    batch_group:     str | None
    batchable:       bool

    @property
    def module_ids(self) -> list[str]:
        return [m.id for m in self.modules]

    @property
    def job_type(self) -> str:
        if self.batchable and self.batch_group:
            return self.batch_group
        return self.modules[0].id

    @property
    def usage_type(self) -> str:
        return {
            "fast_queue":     "fast",
            "standard_queue": "standard",
            "heavy_queue":    "heavy",
            "sandbox_queue":  "sandbox",
        }[self.queue_name]


def create_analysis_plan(selected_modules: list[AnalysisModule]) -> list[AnalysisJobPlan]:
    """Group `selected_modules` into the minimal set of jobs.

    Batchable modules are keyed by (batch_group, queue_name, runtime_image,
    isolation_level) — all four must match, because a single job is a single
    container invocation on a single queue. Non-batchable modules each get
    their own AnalysisJobPlan regardless of any shared attributes.
    """
    batched: dict[tuple[str, str, str, str], list[AnalysisModule]] = {}
    standalone: list[AnalysisModule] = []

    for module in selected_modules:
        if module.batchable and module.batch_group:
            key = (
                module.batch_group,
                module.queue_name,
                module.runtime_image,
                module.isolation_level,
            )
            batched.setdefault(key, []).append(module)
        else:
            standalone.append(module)

    plan: list[AnalysisJobPlan] = []

    for (batch_group, queue_name, runtime_image, isolation_level), modules in batched.items():
        plan.append(AnalysisJobPlan(
            modules=modules,
            queue_name=queue_name,
            runtime_image=runtime_image,
            isolation_level=isolation_level,
            batch_group=batch_group,
            batchable=True,
        ))

    for module in standalone:
        plan.append(AnalysisJobPlan(
            modules=[module],
            queue_name=module.queue_name,
            runtime_image=module.runtime_image,
            isolation_level=module.isolation_level,
            batch_group=None,
            batchable=False,
        ))

    return plan
