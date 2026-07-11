from app.core.security.permission_registry import Permission, register_permissions

CATEGORY_VIEW = Permission("categories", "view", "Categories", "View module categories")
CATEGORY_EDIT = Permission("categories", "edit", "Categories", "Create and edit module categories")

register_permissions(CATEGORY_VIEW, CATEGORY_EDIT)
