from app.core.security.permission_registry import Permission, register_permissions

FINANCE_VIEW = Permission("finance", "view", "Finance", "View transactions, coupons, and discounts")
FINANCE_MANAGE = Permission("finance", "manage", "Finance", "Create and edit coupons and org discounts")

register_permissions(FINANCE_VIEW, FINANCE_MANAGE)
