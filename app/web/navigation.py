from flask import redirect, url_for

from .params import PageSelection


def editor_redirect(selection=None):
    if selection is None:
        return redirect(url_for("editor.edit_page"))

    params = {
        "region": selection.region,
        "year": selection.year,
        "mode": selection.mode,
    }
    if selection.effective_date is not None:
        params["effective_date"] = selection.effective_date.isoformat()
    return redirect(url_for("editor.edit_page", **params))
