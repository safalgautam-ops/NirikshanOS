"""Custom input validation.

Planned for Week 2/3: a Form base class that, like Model, declares
Field attributes (from app/core/db/fields.py). Form.validate(data) runs
each field's validate() and collects errors for the route to re-render
with messages - no external validation library.
"""
