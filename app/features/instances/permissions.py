from app.core.security.permission_registry import Permission, register_permissions

INSTANCE_VIEW = Permission("instances", "view", "Instances", "View registered container instances")
INSTANCE_EDIT = Permission("instances", "edit", "Instances", "Register and edit container instances")

register_permissions(INSTANCE_VIEW, INSTANCE_EDIT)
