import datetime
import os
import tempfile

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from . import card_info, config
from .card_list_parser import CardListParser
from .models import BanList, BanListCard, BanListCardChange, db

main = Blueprint("main", __name__)


def _latest_effective_date(region):
    latest_ban_list = BanList.query.filter_by(region=region).order_by(BanList.effective_date.desc()).first()
    if latest_ban_list is not None:
        return latest_ban_list.effective_date
    return datetime.date.today()


def _parse_effective_date(source, region=None, use_latest_default=True):
    raw_effective_date = source.get("effective_date")
    if raw_effective_date:
        try:
            return datetime.date.fromisoformat(raw_effective_date)
        except ValueError:
            return None

    year = source.get("year")
    month = source.get("month")
    day = source.get("day", 1)
    if year and month:
        try:
            return datetime.date(int(year), int(month), int(day))
        except ValueError:
            return None

    if use_latest_default and region is not None:
        return _latest_effective_date(region)

    return datetime.date.today()


def _get_ban_list_exact(region, effective_date, create=False):
    ban_list = BanList.query.filter_by(region=region, effective_date=effective_date).first()
    if ban_list is None and create:
        ban_list = BanList(region=region, effective_date=effective_date)
        db.session.add(ban_list)
        db.session.flush()
    return ban_list


def _get_ban_list_as_of(region, effective_date):
    return (BanList.query
            .filter(BanList.region == region)
            .filter(BanList.effective_date <= effective_date)
            .order_by(BanList.effective_date.desc())
            .first())


def _get_ban_lists_for_year(region, year):
    start_date = datetime.date(year, 1, 1)
    end_date = datetime.date(year, 12, 31)
    return (BanList.query
            .filter(BanList.region == region)
            .filter(BanList.effective_date >= start_date)
            .filter(BanList.effective_date <= end_date)
            .order_by(BanList.effective_date.asc())
            .all())


def _select_ban_list_for_year(region, year, effective_date=None):
    year_ban_lists = _get_ban_lists_for_year(region, year)
    if effective_date is not None:
        for ban_list in year_ban_lists:
            if ban_list.effective_date == effective_date:
                return ban_list, year_ban_lists
    if year_ban_lists:
        return year_ban_lists[-1], year_ban_lists
    return None, year_ban_lists


def _effective_date_context(effective_date):
    return {
        "selected_effective_date": effective_date.isoformat(),
        "selected_year": effective_date.year,
        "selected_month": effective_date.month,
        "selected_day": effective_date.day,
    }


def _redirect_edit_page(region, year=None, effective_date=None, mode=None):
    params = {
        "region": region,
    }
    if year is not None:
        params["year"] = year
    if effective_date is not None:
        params["effective_date"] = effective_date.isoformat()
    if mode is not None:
        params["mode"] = mode
    return redirect(url_for("main.edit_page", **params))


def _get_card_data_map(cids):
    card_map = {}
    for cid in set(cids):
        card_map[cid] = card_info.get_card_data_by_id(cid)
    return card_map


def _serialize_cards_for_edit(ban_list):
    if ban_list is None:
        return []

    ban_cards = BanListCard.query.filter_by(ban_list_id=ban_list.id).all()
    changes = BanListCardChange.query.filter_by(ban_list_id=ban_list.id).all()
    change_map = {change.card_id: change for change in changes}
    card_info_map = _get_card_data_map([card.cid for card in ban_cards])

    cards = []
    for ban_card in ban_cards:
        card_data = card_info_map.get(ban_card.cid)
        change = change_map.get(ban_card.id)
        cards.append({
            "ban_card_id": ban_card.id,
            "cid": ban_card.cid,
            "name": card_data["name"] if card_data is not None else "未知卡片",
            "old_status": change.old_status if change else ban_card.status,
            "status": ban_card.status,
            "notes": ban_card.notes,
        })

    return sorted(cards, key=lambda item: (item["status"], item["cid"]))


def _sync_change_record(ban_list_id, card_id, old_status, new_status):
    change = BanListCardChange.query.filter_by(ban_list_id=ban_list_id, card_id=card_id).first()
    if change is None:
        change = BanListCardChange(
            ban_list_id=ban_list_id,
            card_id=card_id,
            old_status=old_status,
            new_status=new_status,
        )
        db.session.add(change)
        return change

    change.old_status = old_status
    change.new_status = new_status
    return change


def _resolve_card_name(cid):
    card_data = card_info.get_card_data_by_id(cid)
    if card_data is None:
        return "未知卡片"
    return card_data.get("name", "未知卡片")


def _classify_change(old_status, new_status):
    if old_status is None or new_status is None:
        return "", ""
    if old_status == new_status:
        return "", ""
    if old_status == 3 and new_status == 0:
        return "新规禁止", "change-tight"
    if old_status == 3 and new_status < 3:
        if new_status == 1:
            return "新规限制", "change-tight"
        if new_status == 2:
            return "新规准限制", "change-tight"
    if new_status == 0 and old_status in (1, 2, 3):
        return "新规禁止", "change-tight"
    if new_status < old_status:
        return f"{config.STATUS_MAP[old_status]}=>{config.STATUS_MAP[new_status]}", "change-tight"
    if old_status < 3 and new_status == 3:
        return f"{config.STATUS_MAP[old_status]}=>{config.STATUS_MAP[new_status]}", "change-loose"
    if new_status > old_status:
        return f"{config.STATUS_MAP[old_status]}=>{config.STATUS_MAP[new_status]}", "change-loose"
    return f"{config.STATUS_MAP[old_status]}=>{config.STATUS_MAP[new_status]}", "change-none"

def _classify_change_diff(old_status, new_status):
    if old_status is None or new_status is None:
        return "", ""
    if old_status == new_status:
        return "", ""
    if old_status == 3:
        return "新规指定", "change-tight"
    if new_status == 3:
        return "限制解除", "change-loose"
    if old_status > new_status:
        return "限制加强", "change-tight"
    else:
        return "限制缓和", "change-loose"


def _change_label_order(label):
    order_map = {
        "新规禁止": 0,
        "新规限制": 1,
        "新规准限制": 2,
        "禁止=>限制": 3,
        "禁止=>准限制": 4,
        "限制=>准限制": 5,
        "限制=>无限制": 6,
        "准限制=>无限制": 7,
        "准限制=>限制": 8,
        "限制=>禁止": 9,
        "准限制=>禁止": 10,
        "无限制=>限制": 11,
        "无限制=>准限制": 12,
    }
    return order_map.get(label, 9)


def _card_type_order(card_type):
    order_map = {
        1: 0,  # 怪兽
        2: 1,  # 魔法
        3: 2,  # 陷阱
        0: 9,  # 未知
    }
    return order_map.get(card_type, 9)


def _is_edit_authenticated():
    return session.get("edit_authenticated", False)


def _require_edit_auth(region=None, year=None, effective_date=None):
    if _is_edit_authenticated():
        return None
    flash("请先输入密码完成验证后再进行修改。")
    if region is not None:
        params = {"region": region}
        if year is not None:
            params["year"] = year
        if effective_date is not None:
            params["effective_date"] = effective_date.isoformat()
        return redirect(url_for("main.edit_page", **params))
    return redirect(url_for("main.edit_page"))

@main.route("/", methods=["GET"])
def main_page():
    region = int(request.args.get("region", 0))
    mode = request.args.get("mode", "changes")
    requested_effective_date = _parse_effective_date(request.args, region=region, use_latest_default=False)
    raw_year = request.args.get("year")
    if raw_year is None and requested_effective_date is not None:
        year = requested_effective_date.year
    else:
        year = int(raw_year or datetime.date.today().year)
    if requested_effective_date is not None and requested_effective_date.year == year:
        selected_ban_list, year_ban_lists = _select_ban_list_for_year(region, year, requested_effective_date)
    else:
        selected_ban_list, year_ban_lists = _select_ban_list_for_year(region, year, None)

    selected_effective_date = selected_ban_list.effective_date.isoformat() if selected_ban_list else ""
    upload_info = {
        "selected_year": year,
        "selected_region": region,
        "selected_mode": mode,
        "selected_effective_date": selected_effective_date,
        "selected_active_effective_date": selected_effective_date,
        "year_ban_lists": year_ban_lists,
        "year_options": list(range(max(datetime.date.today().year, year), 2003, -1)),
        "status_map": config.STATUS_MAP,
        "status_class_map": config.STATUS_CLASS_MAP,
        "card_type_map": config.CARD_TYPE_MAP,
    }

    if selected_ban_list is None:
        if mode == "full":
            upload_info["status_sections"] = [
                {"status": 0, "title": config.STATUS_MAP[0], "cards": []},
                {"status": 1, "title": config.STATUS_MAP[1], "cards": []},
                {"status": 2, "title": config.STATUS_MAP[2], "cards": []},
                {"status": 3, "title": config.STATUS_MAP[3], "cards": []},
            ]
        return render_template(f"{mode}.html", cards=[], ban_list=None, **upload_info)

    if mode == "full":
        ban_cards = BanListCard.query.filter_by(ban_list_id=selected_ban_list.id).all()
        changes = BanListCardChange.query.filter_by(ban_list_id=selected_ban_list.id).all()
        change_map = {change.card_id: change for change in changes}
        card_info_map = _get_card_data_map([card.cid for card in ban_cards])

        grouped_cards = {0: [], 1: [], 2: [], 3: []}
        for card in ban_cards:
            card_data = card_info_map.get(card.cid)
            change = change_map.get(card.id)
            old_status = change.old_status if change else card.status
            change_label = ""
            change_class = ""
            if change and change.old_status != card.status:
                change_label, change_class = _classify_change(change.old_status, card.status)

            card_payload = {
                "id": card.cid,
                "name": card_data["name"] if card_data is not None else "未知卡片",
                "type": card_data["type"] if card_data is not None else 0,
                "status": card.status,
                "old_status": old_status,
                "notes": card.notes or "",
                "change_label": change_label,
                "change_class": change_class,
            }
            grouped_cards.setdefault(card.status, []).append(card_payload)

        for status_key in grouped_cards:
            grouped_cards[status_key] = sorted(
                grouped_cards[status_key],
                key=lambda x: (_card_type_order(x.get("type", 0)), x["id"])
            )

        status_sections = [
            {"status": 0, "title": config.STATUS_MAP[0], "cards": grouped_cards.get(0, [])},
            {"status": 1, "title": config.STATUS_MAP[1], "cards": grouped_cards.get(1, [])},
            {"status": 2, "title": config.STATUS_MAP[2], "cards": grouped_cards.get(2, [])},
            {"status": 3, "title": config.STATUS_MAP[3], "cards": grouped_cards.get(3, [])},
        ]
        return render_template("full.html", status_sections=status_sections, **upload_info)

    changes = BanListCardChange.query.filter_by(ban_list_id=selected_ban_list.id).all()
    card_id_to_card = {
        card.id: card
        for card in BanListCard.query
            .filter(BanListCard.id.in_([change.card_id for change in changes]))
            .all()
    } if changes else {}
    card_id_to_cid = {card_id: card.cid for card_id, card in card_id_to_card.items()}
    card_info_map = _get_card_data_map(card_id_to_cid.values())

    cards = []
    for change in changes:
        cid = card_id_to_cid.get(change.card_id)
        if cid is None:
            continue
        card_data = card_info_map.get(cid)
        card = card_id_to_card.get(change.card_id)
        change_label, change_class = _classify_change_diff(change.old_status, change.new_status)
        if card_data is not None:
            cards.append({
                "id": cid,
                "name": card_data["name"],
                "type": card_data["type"],
                "old_status": change.old_status,
                "status": change.new_status,
                "notes": (card.notes or "") if card else "",
                "change_label": change_label,
                "change_class": change_class,
            })
        else:
            cards.append({
                "id": cid,
                "name": "未知卡片",
                "type": 0,
                "old_status": change.old_status,
                "status": change.new_status,
                "notes": (card.notes or "") if card else "",
                "change_label": change_label,
                "change_class": change_class,
            })
    cards = sorted(
        cards,
        key=lambda x: (
            x["status"],
            _change_label_order(x.get("change_label", "")),
            _card_type_order(x.get("type", 0)),
            x["id"],
        )
    )
    return render_template("changes.html", cards=cards, **upload_info)


@main.route("/edit", methods=["GET"])
def edit_page():
    try:
        region = int(request.args.get("region", 0))
    except ValueError:
        flash("时间或环境参数不合法。")
        return redirect(url_for("main.edit_page"))

    requested_effective_date = _parse_effective_date(request.args, region=region, use_latest_default=False)
    raw_year = request.args.get("year")
    if raw_year is None and requested_effective_date is not None:
        year = requested_effective_date.year
    else:
        year = int(raw_year or datetime.date.today().year)
    if requested_effective_date is not None and requested_effective_date.year == year:
        ban_list, year_ban_lists = _select_ban_list_for_year(region, year, requested_effective_date)
    else:
        ban_list, year_ban_lists = _select_ban_list_for_year(region, year, None)

    selected_effective_date = ban_list.effective_date.isoformat() if ban_list else ""
    upload_info = {
        **_effective_date_context(ban_list.effective_date if ban_list else datetime.date(year, 1, 1)),
        "selected_year": year,
        "selected_region": region,
        "selected_mode": request.args.get("mode", "changes"),
        "selected_effective_date": selected_effective_date,
        "selected_active_effective_date": selected_effective_date,
        "year_ban_lists": year_ban_lists,
        "year_options": list(range(max(datetime.date.today().year, year), 2003, -1)),
        "status_map": config.STATUS_MAP,
        "status_class_map": config.STATUS_CLASS_MAP,
        "card_type_map": config.CARD_TYPE_MAP,
        "edit_authenticated": _is_edit_authenticated(),
    }
    return render_template(
        "edit.html",
        cards=_serialize_cards_for_edit(ban_list),
        ban_list=ban_list,
        **upload_info,
    )


@main.route("/edit/create", methods=["POST"])
def create_edit_banlist():
    try:
        region = int(request.form.get("region", 0))
        year = int(request.form.get("year", datetime.date.today().year))
    except ValueError:
        flash("时间或环境参数不合法。")
        return redirect(url_for("main.edit_page"))

    effective_date = _parse_effective_date(request.form, region=region, use_latest_default=False)
    if effective_date is None:
        flash("请输入有效的生效日期。")
        return redirect(url_for("main.edit_page", region=region, year=year))

    if effective_date.year != year:
        flash("生效日期必须属于当前选择的年份。")
        return redirect(url_for("main.edit_page", region=region, year=year))

    auth_redirect = _require_edit_auth(region=region, year=year, effective_date=effective_date)
    if auth_redirect is not None:
        return auth_redirect

    use_csv = request.form.get("use_csv", "no") == "yes"
    card_rows = []
    temp_path = ""

    if use_csv:
        file = request.files.get("banlist_csv")
        if file is None or file.filename == "":
            flash("已选择从文件创建，但未上传 CSV 文件。")
            return redirect(url_for("main.edit_page", region=region, year=year))
        if not file.filename.lower().endswith(".csv"):
            flash("仅支持上传 .csv 文件。")
            return redirect(url_for("main.edit_page", region=region, year=year))

        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            file.save(temp_file)
            temp_path = temp_file.name

        parser = CardListParser(temp_path)
        card_rows = parser.parse()
        if not card_rows:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            flash("CSV 解析失败或内容为空，请检查列名是否为 id,past,current。")
            return redirect(url_for("main.edit_page", region=region, year=year))

    existing = _get_ban_list_exact(region, effective_date)
    if existing is None:
        try:
            existing = BanList(region=region, effective_date=effective_date)
            db.session.add(existing)
            db.session.flush()

            added_count = 0
            if use_csv:
                for row in card_rows:
                    cid = int(row.get("id", 0))
                    old_status = int(row.get("past", 3))
                    new_status = int(row.get("current", 3))
                    if cid <= 0:
                        continue
                    if old_status not in config.STATUS_MAP or new_status not in config.STATUS_MAP:
                        continue

                    card = BanListCard(
                        cid=cid,
                        ban_list_id=existing.id,
                        status=new_status,
                        date_added=effective_date,
                        region=region,
                    )
                    db.session.add(card)
                    db.session.flush()
                    _sync_change_record(existing.id, card.id, old_status, new_status)
                    added_count += 1

            db.session.commit()
            if use_csv:
                flash(f"已创建 {effective_date.isoformat()} 的禁卡表，并从 CSV 导入 {added_count} 张卡片。")
            else:
                flash(f"已创建 {effective_date.isoformat()} 的禁卡表。")
        except Exception as e:
            db.session.rollback()
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            flash(f"创建禁卡表失败：{e}")
            return redirect(url_for("main.edit_page", region=region, year=year))
    else:
        flash(f"{effective_date.isoformat()} 的禁卡表已存在。")

    if temp_path and os.path.exists(temp_path):
        os.unlink(temp_path)

    return _redirect_edit_page(region, year=year, effective_date=effective_date, mode=request.form.get("mode", "changes"))


@main.route("/edit/change-date", methods=["POST"])
def change_edit_banlist_date():
    try:
        region = int(request.form.get("region", 0))
        year = int(request.form.get("year", datetime.date.today().year))
    except ValueError:
        flash("时间或环境参数不合法。")
        return redirect(url_for("main.edit_page"))

    current_effective_date = _parse_effective_date(request.form, region=region, use_latest_default=False)
    raw_new_effective_date = request.form.get("new_effective_date", "").strip()
    mode = request.form.get("mode", "changes")

    if current_effective_date is None:
        flash("当前禁卡表日期参数不合法。")
        return _redirect_edit_page(region, year=year, mode=mode)

    try:
        new_effective_date = datetime.date.fromisoformat(raw_new_effective_date)
    except ValueError:
        flash("新的生效日期格式不合法。")
        return _redirect_edit_page(region, year=year, effective_date=current_effective_date, mode=mode)

    auth_redirect = _require_edit_auth(region=region, year=year, effective_date=current_effective_date)
    if auth_redirect is not None:
        return auth_redirect

    ban_list = _get_ban_list_exact(region, current_effective_date)
    if ban_list is None:
        flash("未找到要修改时间的禁卡表。")
        return _redirect_edit_page(region, year=year, mode=mode)

    if new_effective_date == current_effective_date:
        flash("新的生效日期与当前一致，无需修改。")
        return _redirect_edit_page(region, year=year, effective_date=current_effective_date, mode=mode)

    conflict_ban_list = _get_ban_list_exact(region, new_effective_date)
    if conflict_ban_list is not None:
        flash(f"{new_effective_date.isoformat()} 已存在禁卡表，无法修改。")
        return _redirect_edit_page(region, year=year, effective_date=current_effective_date, mode=mode)

    try:
        ban_list.effective_date = new_effective_date
        BanListCard.query.filter_by(ban_list_id=ban_list.id).update(
            {"date_added": new_effective_date},
            synchronize_session=False,
        )
        db.session.commit()
        flash(f"已将禁卡表时间从 {current_effective_date.isoformat()} 修改为 {new_effective_date.isoformat()}。")
    except Exception as e:
        db.session.rollback()
        flash(f"修改禁卡表时间失败：{e}")
        return _redirect_edit_page(region, year=year, effective_date=current_effective_date, mode=mode)

    return _redirect_edit_page(region, year=new_effective_date.year, effective_date=new_effective_date, mode=mode)


@main.route("/edit/delete", methods=["POST"])
def delete_edit_banlist():
    try:
        region = int(request.form.get("region", 0))
        year = int(request.form.get("year", datetime.date.today().year))
    except ValueError:
        flash("时间或环境参数不合法。")
        return redirect(url_for("main.edit_page"))

    effective_date = _parse_effective_date(request.form, region=region, use_latest_default=False)
    mode = request.form.get("mode", "changes")
    if effective_date is None:
        flash("禁卡表日期参数不合法。")
        return _redirect_edit_page(region, year=year, mode=mode)

    if request.form.get("confirm_delete") != "yes":
        flash("删除操作需要确认后才能提交。")
        return _redirect_edit_page(region, year=year, effective_date=effective_date, mode=mode)

    auth_redirect = _require_edit_auth(region=region, year=year, effective_date=effective_date)
    if auth_redirect is not None:
        return auth_redirect

    ban_list = _get_ban_list_exact(region, effective_date)
    if ban_list is None:
        flash("未找到要删除的禁卡表。")
        return _redirect_edit_page(region, year=year, mode=mode)

    try:
        BanListCardChange.query.filter_by(ban_list_id=ban_list.id).delete(synchronize_session=False)
        BanListCard.query.filter_by(ban_list_id=ban_list.id).delete(synchronize_session=False)
        db.session.delete(ban_list)
        db.session.commit()
        flash(f"已删除 {effective_date.isoformat()} 禁卡表。")
    except Exception as e:
        db.session.rollback()
        flash(f"删除禁卡表失败：{e}")
        return _redirect_edit_page(region, year=year, effective_date=effective_date, mode=mode)

    return _redirect_edit_page(region, year=year, mode=mode)


@main.route("/edit/login", methods=["POST"])
def edit_login():
    password = request.form.get("password", "")
    region = int(request.form.get("region", 0))
    year = int(request.form.get("year", datetime.date.today().year))
    effective_date = _parse_effective_date(request.form, region=region, use_latest_default=False)
    mode = request.form.get("mode", "changes")

    if password == "" or password != current_app.config.get("EDIT_PASSWORD", ""):
        flash("密码错误。")
        return _redirect_edit_page(region, year=year, effective_date=effective_date, mode=mode)

    session["edit_authenticated"] = True
    flash("验证成功，可以进行修改。")
    return _redirect_edit_page(region, year=year, effective_date=effective_date, mode=mode)


@main.route("/edit/logout", methods=["POST"])
def edit_logout():
    session.pop("edit_authenticated", None)
    flash("已退出修改权限。")
    region = int(request.form.get("region", 0))
    year = int(request.form.get("year", datetime.date.today().year))
    effective_date = _parse_effective_date(request.form, region=region, use_latest_default=False)
    mode = request.form.get("mode", "changes")
    return _redirect_edit_page(region, year=year, effective_date=effective_date, mode=mode)


@main.route("/edit", methods=["POST"])
def edit_banlist_card():
    try:
        region = int(request.form.get("region", 0))
        year = int(request.form.get("year", datetime.date.today().year))
    except ValueError:
        flash("时间或环境参数不合法。")
        return redirect(url_for("main.edit_page"))

    effective_date = _parse_effective_date(request.form, region=region, use_latest_default=False)
    if effective_date is None:
        flash("日期参数不合法。")
        return redirect(url_for("main.edit_page", region=region, year=year))

    auth_redirect = _require_edit_auth(region=region, year=year, effective_date=effective_date)
    if auth_redirect is not None:
        return auth_redirect

    operation = request.form.get("operation", "add")
    ban_list = _get_ban_list_exact(region, effective_date, create=(operation == "add"))

    if ban_list is None:
        flash("该时间点还没有禁卡表，请先新增卡片。")
        return _redirect_edit_page(region, year=year, effective_date=effective_date)

    try:
        if operation == "add":
            cid = request.form.get("cid")
            name = request.form.get("name", "").strip()
            notes = request.form.get("notes", "").strip()
            if not notes:
                notes = None
            old_status = int(request.form.get("old_status", 3))
            new_status = int(request.form.get("new_status", 3))
            if not cid and not name:
                flash("请至少提供 CID 或卡名中的一个。")
                return _redirect_edit_page(region, year=year, effective_date=effective_date)
            if not cid:
                card_data = card_info.get_card_data_by_name(name)
                if card_data is None:
                    flash("未找到对应卡片，请检查卡名是否正确。")
                    return _redirect_edit_page(region, year=year, effective_date=effective_date)
                cid = card_data["id"]
            else:
                try:
                    cid = int(cid)
                except ValueError:
                    flash("CID 必须是有效数字。")
                    return _redirect_edit_page(region, year=year, effective_date=effective_date)
            if cid <= 0:
                flash("CID 必须是有效数字。")
                return _redirect_edit_page(region, year=year, effective_date=effective_date)
            if old_status not in config.STATUS_MAP or new_status not in config.STATUS_MAP:
                flash("状态值不合法。")
                return _redirect_edit_page(region, year=year, effective_date=effective_date)
            existing = BanListCard.query.filter_by(ban_list_id=ban_list.id, cid=cid).first()
            card_name = _resolve_card_name(cid)
            if existing is None:
                card = BanListCard(
                    cid=cid,
                    ban_list_id=ban_list.id,
                    status=new_status,
                    date_added=effective_date,
                    region=region,
                    notes=notes,
                )
                db.session.add(card)
                db.session.flush()
                _sync_change_record(ban_list.id, card.id, old_status, new_status)
                flash(f"已新增 CID {cid} - {card_name}。")
            else:
                existing.status = new_status
                existing.date_added = effective_date
                existing.region = region
                if notes is not None:
                    existing.notes = notes
                _sync_change_record(ban_list.id, existing.id, old_status, new_status)
                flash(f"CID {cid} - {card_name} 已存在，已转为更新。")

        elif operation == "update":
            card_id = int(request.form.get("card_id", 0))
            old_status = int(request.form.get("old_status", 3))
            new_status = int(request.form.get("new_status", 3))
            notes = request.form.get("notes", "").strip()
            if not notes:
                notes = None
            card = BanListCard.query.filter_by(id=card_id, ban_list_id=ban_list.id).first()
            if card is None:
                flash("未找到要更新的卡片。")
                return _redirect_edit_page(region, year=year, effective_date=effective_date)
            name = _resolve_card_name(card.cid)
            if old_status not in config.STATUS_MAP or new_status not in config.STATUS_MAP:
                flash("状态值不合法。")
                return _redirect_edit_page(region, year=year, effective_date=effective_date)

            card.status = new_status
            card.notes = notes
            _sync_change_record(ban_list.id, card.id, old_status, new_status)
            flash(f"已更新 CID {card.cid} - {name}。")

        elif operation == "delete":
            card_id = int(request.form.get("card_id", 0))
            card = BanListCard.query.filter_by(id=card_id, ban_list_id=ban_list.id).first()
            if card is None:
                flash("未找到要删除的卡片。")
                return _redirect_edit_page(region, year=year, effective_date=effective_date)
            name = _resolve_card_name(card.cid)
            BanListCardChange.query.filter_by(ban_list_id=ban_list.id, card_id=card.id).delete(synchronize_session=False)
            db.session.delete(card)
            flash(f"已删除 CID {card.cid} - {name}。")

        else:
            flash("不支持的操作类型。")
            return _redirect_edit_page(region, year=year, effective_date=effective_date)

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f"操作失败：{e}")

    return _redirect_edit_page(region, year=year, effective_date=effective_date)


@main.route("/upload", methods=["POST"])
def upload_banlist_csv():
    try:
        region = int(request.form.get("region", 0))
        year = int(request.form.get("year", datetime.date.today().year))
    except ValueError:
        flash("时间或环境参数不合法。")
        return redirect(url_for("main.edit_page"))

    effective_date = _parse_effective_date(request.form, region=region, use_latest_default=False)
    if effective_date is None:
        flash("日期参数不合法。")
        return redirect(url_for("main.edit_page", region=region, year=year))

    auth_redirect = _require_edit_auth(region=region, year=year, effective_date=effective_date)
    if auth_redirect is not None:
        return auth_redirect

    upload_mode = request.form.get("upload_mode", "append")
    if upload_mode not in {"append", "overwrite"}:
        flash("上传模式不合法。")
        return _redirect_edit_page(region, year=year, effective_date=effective_date)

    if upload_mode == "overwrite" and request.form.get("confirm_overwrite") != "yes":
        flash("覆盖模式需要确认后才能提交。")
        return _redirect_edit_page(region, year=year, effective_date=effective_date)

    file = request.files.get("banlist_csv")
    if file is None or file.filename == "":
        flash("请先选择一个 CSV 文件。")
        return _redirect_edit_page(region, year=year, effective_date=effective_date)

    if not file.filename.lower().endswith(".csv"):
        flash("仅支持上传 .csv 文件。")
        return _redirect_edit_page(region, year=year, effective_date=effective_date)

    temp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as temp_file:
            file.save(temp_file)
            temp_path = temp_file.name

        parser = CardListParser(temp_path)
        card_rows = parser.parse()
        if not card_rows:
            flash("CSV 解析失败或内容为空，请检查列名是否为 id,past,current。")
            return _redirect_edit_page(region, year=year, effective_date=effective_date)

        ban_list = _get_ban_list_exact(region, effective_date, create=True)

        added_count = 0
        updated_count = 0

        if upload_mode == "overwrite":
            # 覆盖更新：先删除该时间点旧数据，再写入新 CSV。
            old_cards = BanListCard.query.filter_by(ban_list_id=ban_list.id).all()
            old_card_ids = [card.id for card in old_cards]
            if old_card_ids:
                BanListCardChange.query.filter(BanListCardChange.card_id.in_(old_card_ids)).delete(synchronize_session=False)
            BanListCard.query.filter_by(ban_list_id=ban_list.id).delete(synchronize_session=False)
            existing_map = {}
        else:
            existing_map = {
                card.cid: card
                for card in BanListCard.query.filter_by(ban_list_id=ban_list.id).all()
            }

        for row in card_rows:
            cid = int(row.get("id", 0))
            old_status = int(row.get("past", 3))
            new_status = int(row.get("current", 3))
            if cid <= 0:
                continue
            if old_status not in config.STATUS_MAP or new_status not in config.STATUS_MAP:
                continue

            existing = existing_map.get(cid)
            if existing is None:
                card = BanListCard(
                    cid=cid,
                    ban_list_id=ban_list.id,
                    status=new_status,
                    date_added=effective_date,
                    region=region,
                )
                db.session.add(card)
                db.session.flush()
                _sync_change_record(ban_list.id, card.id, old_status, new_status)
                existing_map[cid] = card
                added_count += 1
            else:
                existing.status = new_status
                existing.date_added = effective_date
                existing.region = region
                _sync_change_record(ban_list.id, existing.id, old_status, new_status)
                updated_count += 1

        db.session.commit()
        if upload_mode == "overwrite":
            flash(f"已覆盖更新 {effective_date.isoformat()} 禁卡表，新增 {added_count}，更新 {updated_count}。")
        else:
            flash(f"已追加更新 {effective_date.isoformat()} 禁卡表，新增 {added_count}，更新 {updated_count}。")
    except Exception as e:
        db.session.rollback()
        flash(f"更新失败：{e}")
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)

    return _redirect_edit_page(region, year=year, effective_date=effective_date)