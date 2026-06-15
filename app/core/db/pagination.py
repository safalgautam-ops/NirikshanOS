"""Pagination helper.

Wraps QueryBuilder with LIMIT/OFFSET and a COUNT(*) query, returning a
Page object consumed by templates/components/ui/pagination.html.

Pagination is the "showing 1–20 of 137" thing you see on websites. When a list is too long to dump on one screen,
you split it into pages and show one page at a time, with "next"/"previous" buttons.

@dataclass.
Normally, to make a class that just holds some data, you'd write a fair bit of boilerplate
(an __init__ that stores each value, etc.). A @dataclass is a shortcut: you just list the fields you want,
and Python automatically writes that boilerplate for you. It's for classes whose main job is "hold a few related values together."

@property. Normally, calling a method needs parentheses: page.total_pages().
A @property lets you write a method but access it like a plain attribute — page.total_pages, no parentheses.
It's used for values that are computed on demand from other data. Why bother? Because total_pages isn't a stored fact —
it's derived from total and per_page. A property lets you compute it fresh each time you ask,
while still reading like a simple attribute.

The imports at the top:

pythonfrom dataclasses import dataclass
from app.core.db.model import Model
from app.core.db.query_builder import QueryBuilder

These just pull in the tools this file uses: dataclass (the shortcut above), Model (the base class from File 3), and QueryBuilder (the query-building tool we'll lean on).
"""

from dataclasses import dataclass

from app.core.db.model import Model
from app.core.db.query_builder import QueryBuilder


@dataclass
# data container with 4 fields: items, page, per_page, and total.
# A page object is a container that answers "you're on page 3 of pages holding 20 each out, out of 137 total"
class Page:
    items: list  # actual rows on this page (e.g. 20 records you're currently showing)
    page: int  # current page number (starts at 1)
    per_page: int  # how many rows fit on a page (e.g. 20)
    total: int  # total number of items across all pages (e.g 137)

    @property
    def total_pages(self) -> int:
        if self.per_page <= 0:
            return 0
        # Ceiling division(rounding up) so a partial last page still counts as a page.
        # e.g. 137 total items, 20 per page -> 7 pages (137/20 = 6.8, rounded up to 7)
        # round up using round-down division (add per_page-1 to total before dividing)
        # adding per_page-1 nudges any partial page up to the next whole number, while leaving exact multiples untouched.
        # standard idiom for "ceiling division" when you have only floor division available
        # // is floor division; the result is rounded down to the nearest integer
        return (self.total + self.per_page - 1) // self.per_page

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1


# function call to get a page (builds and run the queries, then packages the reuslt into a Page)
async def paginate(
    # model: the model class to paginate (e.g. User): which table to paginate
    # page: the page number to fetch (default 1)
    # per_page: how many items per page (default 20)
    # where: optional filters to apply to the query (e.g. name="anna")
    # * forces the following arguments to be passed by name.
    model: type[Model],
    *,
    page: int = 1,
    per_page: int = 20,
    **where,
) -> Page:  # returns the page object (the above container)
    # Clamp to page 1 so a bad/negative `page` query param can't produce a
    # negative OFFSET.
    page = max(page, 1)  # ensure page is at least 1 (use whichever is larger)
    offset = (
        page - 1
    ) * per_page  # offset is how many rows to skip to reach the start of your page
    # page 1 skips nothing (you start at row 0)
    # page 2 skips 20 rows (you start at row 20)
    # so the formula page 2 -> offset = (2 - 1) * 20 = 20 rows skipped

    # Two separate builders: one for the page of rows (LIMIT/OFFSET applied),
    # one for the total count (no LIMIT) - same WHERE filters on both.
    query = QueryBuilder(model)
    count_query = QueryBuilder(model)
    for field, value in where.items():
        query.where(field, value)
        count_query.where(field, value)

    # Fetch only this page's rows.
    items = await query.limit(per_page, offset).all()

    # COUNT(*) instead of fetching every matching row just to call len().
    total = await count_query.count()

    return Page(items=items, page=page, per_page=per_page, total=total)
