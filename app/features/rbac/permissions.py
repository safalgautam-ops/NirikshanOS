from app.core.security.permission_registry import Permission, register_permissions

ROLE_VIEW = Permission("role", "view", "Roles & Permissions", "View roles")
ROLE_CREATE = Permission("role", "create", "Roles & Permissions", "Create roles")
ROLE_EDIT = Permission("role", "edit", "Roles & Permissions", "Edit roles")
ROLE_DELETE = Permission("role", "delete", "Roles & Permissions", "Delete roles")

register_permissions(ROLE_VIEW, ROLE_CREATE, ROLE_EDIT, ROLE_DELETE)
