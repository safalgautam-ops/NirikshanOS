"""Groups selected modules (DB dicts) into the minimal set of analysis jobs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisJobPlan:
    modules:         list[dict]
    queue_name:      str
    runtime_image:   str
    isolation_level: str
    batch_group:     str | None
    batchable:       bool

    @property
    def module_ids(self) -> list[str]:
        return [m["id"] for m in self.modules]

    @property
    def job_type(self) -> str:
        if self.batchable and self.batch_group:
            return self.batch_group
        return self.modules[0]["id"]

    @property
    def usage_type(self) -> str:
        return {
            "fast_queue":     "fast",
            "standard_queue": "standard",
            "heavy_queue":    "heavy",
            "sandbox_queue":  "sandbox",
        }.get(self.queue_name, "standard")


def create_analysis_plan(selected_modules: list[dict]) -> list[AnalysisJobPlan]:
    """Group modules into the minimal set of jobs.

    Batchable modules that share (batch_group, queue_name, runtime_image,
    isolation_level) → one job. Everything else → one job each.
    """
    batched: dict[tuple[str, str, str, str], list[dict]] = {}
    standalone: list[dict] = []

    for mod in selected_modules:
        if mod.get("batchable") and mod.get("batch_group"):
            key = (
                mod["batch_group"],
                mod["queue_name"],
                mod["runtime_image"],
                mod["isolation_level"],
            )
            batched.setdefault(key, []).append(mod)
        else:
            standalone.append(mod)

    plan: list[AnalysisJobPlan] = []

    for (batch_group, queue_name, runtime_image, isolation_level), mods in batched.items():
        plan.append(AnalysisJobPlan(
            modules=mods,
            queue_name=queue_name,
            runtime_image=runtime_image,
            isolation_level=isolation_level,
            batch_group=batch_group,
            batchable=True,
        ))

    for mod in standalone:
        plan.append(AnalysisJobPlan(
            modules=[mod],
            queue_name=mod["queue_name"],
            runtime_image=mod["runtime_image"],
            isolation_level=mod["isolation_level"],
            batch_group=None,
            batchable=False,
        ))

    return plan
