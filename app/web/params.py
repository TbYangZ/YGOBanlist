import datetime
from dataclasses import dataclass

from ..config import BANLIST_REGIONS, VIEW_MODES


class InputError(ValueError):
    pass


def parse_date(value, field_name="生效日期", required=False):
    raw_value = (value or "").strip()
    if not raw_value:
        if required:
            raise InputError(f"请输入有效的{field_name}。")
        return None
    try:
        return datetime.date.fromisoformat(raw_value)
    except ValueError as exc:
        raise InputError(f"{field_name}格式不合法。") from exc


def parse_integer(value, field_name, default=None):
    if value in (None, ""):
        if default is not None:
            return default
        raise InputError(f"{field_name}不能为空。")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise InputError(f"{field_name}参数不合法。") from exc


@dataclass(frozen=True)
class PageSelection:
    region: int
    year: int
    mode: str
    effective_date: datetime.date | None

    @classmethod
    def from_source(cls, source):
        effective_date = parse_date(source.get("effective_date"))
        default_year = (
            effective_date.year
            if effective_date is not None
            else datetime.date.today().year
        )
        region = parse_integer(source.get("region"), "环境", default=0)
        year = parse_integer(source.get("year"), "年份", default=default_year)
        mode = (source.get("mode") or "changes").strip()

        if region not in BANLIST_REGIONS:
            raise InputError("环境参数不合法。")
        if year < 2004 or year > 9999:
            raise InputError("年份参数不合法。")
        if mode not in VIEW_MODES:
            raise InputError("查看类型参数不合法。")

        return cls(
            region=region,
            year=year,
            mode=mode,
            effective_date=effective_date,
        )

    def with_effective_date(self, effective_date):
        return PageSelection(
            region=self.region,
            year=effective_date.year if effective_date else self.year,
            mode=self.mode,
            effective_date=effective_date,
        )
