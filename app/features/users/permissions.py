from app.core.security.permission_registry import Permission, register_permissions

USER_VIEW = Permission("user", "view", "User Management", "View users")
USER_EDIT = Permission("user", "edit", "User Management", "Edit users")
USER_DELETE = Permission("user", "delete", "User Management", "Delete users")

register_permissions(USER_VIEW, USER_EDIT, USER_DELETE)
