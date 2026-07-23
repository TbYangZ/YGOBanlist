from flask import flash, session

from .navigation import editor_redirect


SESSION_KEY = "edit_authenticated"


def is_editor_authenticated():
    return bool(session.get(SESSION_KEY, False))


def require_editor_auth(selection):
    if is_editor_authenticated():
        return None
    flash("请先输入密码完成验证后再进行修改。")
    return editor_redirect(selection)


def log_in_editor():
    session[SESSION_KEY] = True


def log_out_editor():
    session.pop(SESSION_KEY, None)
