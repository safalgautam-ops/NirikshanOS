from app.core.security.permission_registry import Permission, register_permissions

PLAN_VIEW   = Permission("plans", "view",   "Plans", "View subscription plans")
PLAN_EDIT   = Permission("plans", "edit",   "Plans", "Create and edit plans")
PLAN_ASSIGN = Permission("plans", "assign", "Plans", "Assign plans to organizations")

register_permissions(PLAN_VIEW, PLAN_EDIT, PLAN_ASSIGN)
