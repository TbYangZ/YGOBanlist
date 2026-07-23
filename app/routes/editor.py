import hmac

from flask import (
    Blueprint,
    current_app,
    flash,
    render_template,
    request,
)

from ..card_list_parser import CardListParseError, CardListParser
from ..services import banlists, presentation
from ..web.auth import (
    is_editor_authenticated,
    log_in_editor,
    log_out_editor,
    require_editor_auth,
)
from ..web.navigation import editor_redirect
from ..web.params import InputError, PageSelection, parse_date, parse_integer


editor = Blueprint("editor", __name__)


def _selection_from(source):
    try:
        return PageSelection.from_source(source), None
    except InputError as exc:
        flash(str(exc))
        return None, editor_redirect()


def _required_effective_date(selection, message="请输入有效的生效日期。"):
    if selection.effective_date is None:
        raise InputError(message)
    return selection.effective_date


def _uploaded_rows(field_name="banlist_csv"):
    uploaded_file = request.files.get(field_name)
    if uploaded_file is None or not uploaded_file.filename:
        raise InputError("请先选择一个 CSV 文件。")
    if not uploaded_file.filename.lower().endswith(".csv"):
        raise InputError("仅支持上传 .csv 文件。")

    try:
        return CardListParser().parse(uploaded_file.stream)
    except CardListParseError as exc:
        raise InputError(
            "CSV 解析失败或内容为空，请检查三列是否为 id,past,current。"
        ) from exc


def _handle_unexpected_error(action):
    current_app.logger.exception("%s failed", action)
    flash(f"{action}失败，请查看服务日志。")


@editor.get("/manage")
def edit_page():
    selection, error_response = _selection_from(request.args)
    if error_response:
        return error_response
    context = presentation.editor_page(
        selection,
        authenticated=is_editor_authenticated(),
    )
    return render_template("edit.html", **context)


@editor.get("/edit")
def legacy_edit_page():
    selection, error_response = _selection_from(request.args)
    if error_response:
        return error_response
    context = presentation.editor_page(
        selection,
        authenticated=is_editor_authenticated(),
    )
    return render_template("edit.html", **context)


@editor.post("/edit/login")
def edit_login():
    selection, error_response = _selection_from(request.form)
    if error_response:
        return error_response

    supplied_password = request.form.get("password", "")
    configured_password = current_app.config.get("EDIT_PASSWORD", "")
    if (
        not supplied_password
        or not hmac.compare_digest(supplied_password, configured_password)
    ):
        flash("密码错误。")
        return editor_redirect(selection)

    log_in_editor()
    flash("验证成功，可以进行修改。")
    return editor_redirect(selection)


@editor.post("/edit/logout")
def edit_logout():
    selection, error_response = _selection_from(request.form)
    if error_response:
        return error_response
    log_out_editor()
    flash("已退出修改权限。")
    return editor_redirect(selection)


@editor.post("/edit/create")
def create_edit_banlist():
    selection, error_response = _selection_from(request.form)
    if error_response:
        return error_response

    try:
        effective_date = _required_effective_date(selection)
        if effective_date.year != selection.year:
            raise InputError("生效日期必须属于当前选择的年份。")
    except InputError as exc:
        flash(str(exc))
        return editor_redirect(selection.with_effective_date(None))

    auth_response = require_editor_auth(selection)
    if auth_response:
        return auth_response

    rows = None
    use_csv = request.form.get("use_csv", "no") == "yes"
    if use_csv:
        try:
            rows = _uploaded_rows()
        except InputError as exc:
            flash(str(exc))
            return editor_redirect(selection)

    try:
        _, added, created = banlists.create_ban_list(
            selection.region,
            effective_date,
            rows=rows,
        )
        if not created:
            flash(f"{effective_date.isoformat()} 的禁卡表已存在。")
        elif use_csv:
            flash(
                f"已创建 {effective_date.isoformat()} 的禁卡表，"
                f"并从 CSV 导入 {added} 张卡片。"
            )
        else:
            flash(f"已创建 {effective_date.isoformat()} 的禁卡表。")
    except banlists.BanListServiceError as exc:
        flash(str(exc))
    except Exception:
        _handle_unexpected_error("创建禁卡表")
    return editor_redirect(selection)


@editor.post("/edit/change-date")
def change_edit_banlist_date():
    selection, error_response = _selection_from(request.form)
    if error_response:
        return error_response

    try:
        current_date = _required_effective_date(
            selection,
            "当前禁卡表日期参数不合法。",
        )
        new_date = parse_date(
            request.form.get("new_effective_date"),
            field_name="新的生效日期",
            required=True,
        )
    except InputError as exc:
        flash(str(exc))
        return editor_redirect(selection)

    auth_response = require_editor_auth(selection)
    if auth_response:
        return auth_response

    try:
        changed = banlists.change_effective_date(
            selection.region,
            current_date,
            new_date,
        )
        if changed:
            flash(
                f"已将禁卡表时间从 {current_date.isoformat()} "
                f"修改为 {new_date.isoformat()}。"
            )
            selection = selection.with_effective_date(new_date)
        else:
            flash("新的生效日期与当前一致，无需修改。")
    except banlists.BanListServiceError as exc:
        flash(str(exc))
    except Exception:
        _handle_unexpected_error("修改禁卡表时间")
    return editor_redirect(selection)


@editor.post("/edit/delete")
def delete_edit_banlist():
    selection, error_response = _selection_from(request.form)
    if error_response:
        return error_response

    try:
        effective_date = _required_effective_date(
            selection,
            "禁卡表日期参数不合法。",
        )
    except InputError as exc:
        flash(str(exc))
        return editor_redirect(selection)

    if request.form.get("confirm_delete") != "yes":
        flash("删除操作需要确认后才能提交。")
        return editor_redirect(selection)

    auth_response = require_editor_auth(selection)
    if auth_response:
        return auth_response

    try:
        banlists.delete_ban_list(selection.region, effective_date)
        flash(f"已删除 {effective_date.isoformat()} 禁卡表。")
        selection = selection.with_effective_date(None)
    except banlists.BanListServiceError as exc:
        flash(str(exc))
    except Exception:
        _handle_unexpected_error("删除禁卡表")
    return editor_redirect(selection)


@editor.post("/edit")
def edit_banlist_card():
    selection, error_response = _selection_from(request.form)
    if error_response:
        return error_response

    try:
        effective_date = _required_effective_date(
            selection,
            "日期参数不合法。",
        )
    except InputError as exc:
        flash(str(exc))
        return editor_redirect(selection)

    auth_response = require_editor_auth(selection)
    if auth_response:
        return auth_response

    operation = request.form.get("operation", "add")
    try:
        old_status = parse_integer(
            request.form.get("old_status"),
            "之前状态",
            default=3,
        )
        new_status = parse_integer(
            request.form.get("new_status"),
            "当前状态",
            default=3,
        )
        notes = request.form.get("notes", "").strip() or None
        result = banlists.mutate_card(
            operation,
            selection.region,
            effective_date,
            card_id=request.form.get("card_id"),
            cid=request.form.get("cid"),
            name=request.form.get("name", "").strip(),
            old_status=old_status,
            new_status=new_status,
            notes=notes,
        )
        action_messages = {
            "added": f"已新增 CID {result.cid} - {result.name}。",
            "updated": f"已更新 CID {result.cid} - {result.name}。",
            "deleted": f"已删除 CID {result.cid} - {result.name}。",
        }
        flash(action_messages[result.action])
    except (InputError, banlists.BanListServiceError) as exc:
        flash(str(exc))
    except Exception:
        _handle_unexpected_error("卡片操作")
    return editor_redirect(selection)


@editor.post("/upload")
def upload_banlist_csv():
    selection, error_response = _selection_from(request.form)
    if error_response:
        return error_response

    try:
        effective_date = _required_effective_date(
            selection,
            "日期参数不合法。",
        )
    except InputError as exc:
        flash(str(exc))
        return editor_redirect(selection)

    auth_response = require_editor_auth(selection)
    if auth_response:
        return auth_response

    upload_mode = request.form.get("upload_mode", "append")
    if upload_mode not in {"append", "overwrite"}:
        flash("上传模式不合法。")
        return editor_redirect(selection)
    if (
        upload_mode == "overwrite"
        and request.form.get("confirm_overwrite") != "yes"
    ):
        flash("覆盖模式需要确认后才能提交。")
        return editor_redirect(selection)

    try:
        rows = _uploaded_rows()
        result = banlists.import_rows(
            selection.region,
            effective_date,
            rows,
            upload_mode,
        )
        action = "覆盖更新" if upload_mode == "overwrite" else "追加更新"
        flash(
            f"已{action} {effective_date.isoformat()} 禁卡表，"
            f"新增 {result.added}，更新 {result.updated}。"
        )
    except (InputError, banlists.BanListServiceError) as exc:
        flash(str(exc))
    except Exception:
        _handle_unexpected_error("更新禁卡表")
    return editor_redirect(selection)
