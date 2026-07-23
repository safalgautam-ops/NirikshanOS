"""Groups selected modules (DB dicts) into the minimal set of analysis jobs."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.db.orm import db


@dataclass(frozen=True)
class AnalysisJobPlan:
    modules: list[dict]
    instance_id: str
    queue_name: str
    runtime_image: str

    @property
    def module_ids(self) -> list[str]:
        return [m["id"] for m in self.modules]

    @property
    def job_type(self) -> str:
        return self.instance_id if len(self.modules) > 1 else self.modules[0]["id"]

    @property
    def usage_type(self) -> str:
        return {
            "light_queue": "light",
            "medium_queue": "medium",
            "heavy_queue": "heavy",
            "full_queue": "full",
        }.get(self.queue_name, "medium")


async def create_analysis_plan(selected_modules: list[dict]) -> list[AnalysisJobPlan]:
    """Group modules into the minimal set of jobs — one per distinct instance_id."""
    by_instance: dict[str, list[dict]] = {}
    for mod in selected_modules:
        by_instance.setdefault(mod["instance_id"], []).append(mod)

    plan: list[AnalysisJobPlan] = []
    for instance_id, mods in by_instance.items():
        instance = await db.table("instances").where("id", instance_id).first()
        if instance is None:
            raise ValueError(f"Instance '{instance_id}' referenced by a selected module no longer exists.")
        plan.append(
            AnalysisJobPlan(
                modules=mods,
                instance_id=instance_id,
                queue_name=instance["queue_name"],
                runtime_image=instance["image_tag"],
            )
        )

    return plan
