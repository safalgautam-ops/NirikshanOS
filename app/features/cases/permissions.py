from app.core.security.org_permission_registry import OrgPermission, register_org_permissions

# No CASE_VIEW: viewing a case is decided purely by row-level access (org
# owner, the case's creator, or someone explicitly added as a case member -
# see app/features/cases/service.py.can_access_case), never by a role
# permission. A permission here would either do nothing (if not enforced)
# or let a role override who can see a specific case (if enforced) - both
# wrong, so it was deliberately removed rather than left as a dead toggle
# in the Roles editor.
CASE_CREATE = OrgPermission("case", "create", "Cases", "Create cases for this organization")
CASE_EDIT = OrgPermission("case", "edit", "Cases", "Edit case details and members")
CASE_DELETE = OrgPermission("case", "delete", "Cases", "Delete cases")

EVIDENCE_UPLOAD = OrgPermission("evidence", "upload", "Cases", "Upload evidence to a case")
EVIDENCE_DELETE = OrgPermission("evidence", "delete", "Cases", "Delete evidence from a case")
EVIDENCE_ANALYZE = OrgPermission("evidence", "analyze", "Cases", "Run analysis modules against evidence")

register_org_permissions(
    CASE_CREATE,
    CASE_EDIT,
    CASE_DELETE,
    EVIDENCE_UPLOAD,
    EVIDENCE_DELETE,
    EVIDENCE_ANALYZE,
)
