from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..services.presentation import public_page
from ..web.params import InputError, PageSelection


public = Blueprint("public", __name__)


@public.get("/")
def main_page():
    try:
        selection = PageSelection.from_source(request.args)
    except InputError as exc:
        flash(str(exc))
        return redirect(url_for("public.main_page"))

    template, context = public_page(selection)
    return render_template(template, **context)
