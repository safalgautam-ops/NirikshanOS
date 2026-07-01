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

The analysis planner converts selected modules into executable job plans.

It does not check permission and does not execute tools.

Its job is only to decide how many backend jobs are needed.

Safe batchable modules with the same batch group, queue, runtime image,
and isolation level are grouped into one job.

Heavy or non-batchable modules become separate jobs.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.features.analysis.module_registry import (
    AnalysisModule,
    IsolationLevel,
    QueueName,
)


@dataclass(frozen=True)
class AnalysisJobPlan:  # run this module together using this rumtime image, queue, and isolation level
    modules: list[AnalysisModule]  # modules included in this job
    queue_name: QueueName  # which queue this job should go to: fast queue, standard queue, heavy queue, or sandbox queue
    runtime_image: str
    isolation_level: IsolationLevel  # how isolated this job should be: none, sandboxed, network_restricted, or vm
    batch_group: str | None
    batchable: bool

    @property
    def module_ids(self) -> list[str]:  # gives only the IDs of the modules in the job
        return [m.id for m in self.modules]

    # this property defines the type of job: batchable or standalone
    @property
    def job_type(self) -> str:
        if self.batchable and self.batch_group:
            return self.batch_group
        return self.modules[0].id

    @property
    def usage_type(self) -> str:
        return {
            "fast_queue": "fast",
            "standard_queue": "standard",
            "heavy_queue": "heavy",
            "sandbox_queue": "sandbox",
        }[self.queue_name]


def create_analysis_plan(
    selected_modules: list[AnalysisModule],
) -> list[AnalysisJobPlan]:
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
            key = (  # create a unique identity for the batch, it groups by 4 things
                module.batch_group,
                module.queue_name,
                module.runtime_image,
                module.isolation_level,
            )
            batched.setdefault(key, []).append(
                module
            )  # the 4 batches things become key as they are all used to identify a batch and are same
        else:
            standalone.append(module)

    plan: list[AnalysisJobPlan] = []

    for (
        batch_group,
        queue_name,
        runtime_image,
        isolation_level,
    ), modules in batched.items():
        plan.append(
            AnalysisJobPlan(
                modules=modules,
                queue_name=queue_name,
                runtime_image=runtime_image,
                isolation_level=isolation_level,
                batch_group=batch_group,
                batchable=True,
            )
        )

    for module in standalone:
        plan.append(
            AnalysisJobPlan(
                modules=[module],
                queue_name=module.queue_name,
                runtime_image=module.runtime_image,
                isolation_level=module.isolation_level,
                batch_group=None,
                batchable=False,
            )
        )

    return plan
