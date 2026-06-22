from app.core.security.permission_registry import Permission, register_permissions

STAFF_VIEW = Permission("staff", "view", "Staff Management", "View staff")
STAFF_CREATE = Permission("staff", "create", "Staff Management", "Create staff")
STAFF_EDIT = Permission("staff", "edit", "Staff Management", "Edit staff")

register_permissions(STAFF_VIEW, STAFF_CREATE, STAFF_EDIT)
