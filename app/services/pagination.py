"""Pagination commune des listes (requetes SQL et listes Python)."""
import math

from flask import request, url_for

PAGE_SIZES = (25, 50, 100, 200)
DEFAULT_PAGE_SIZE = 50


class Pager:
    def __init__(self, items, page, per_page, total, key="page"):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.key = key
        self.pages = max(1, math.ceil(total / per_page))
        self.has_prev = page > 1
        self.has_next = page < self.pages

    def url(self, page):
        args = request.args.to_dict(flat=True)
        args[self.key] = page
        args["per_page"] = self.per_page
        return url_for(request.endpoint, **(request.view_args or {}), **args)


def _page_params(key):
    per_page = request.args.get("per_page", default=DEFAULT_PAGE_SIZE, type=int)
    if per_page not in PAGE_SIZES:
        per_page = DEFAULT_PAGE_SIZE
    page = request.args.get(key, default=1, type=int) or 1
    return page, per_page


def paginate(query, key="page"):
    """Pagine une requete SQLAlchemy (l'ordre doit etre defini par l'appelant)."""
    page, per_page = _page_params(key)
    total = query.order_by(None).count()
    pages = max(1, math.ceil(total / per_page))
    page = min(max(page, 1), pages)
    items = query.limit(per_page).offset((page - 1) * per_page).all()
    return Pager(items, page, per_page, total, key)


def paginate_list(sequence, key="page"):
    """Pagine une liste Python deja filtree."""
    page, per_page = _page_params(key)
    total = len(sequence)
    pages = max(1, math.ceil(total / per_page))
    page = min(max(page, 1), pages)
    start = (page - 1) * per_page
    return Pager(sequence[start:start + per_page], page, per_page, total, key)
