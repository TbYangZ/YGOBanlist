import pandas as pd


class CardListParseError(ValueError):
    pass


class CardListParser:
    COLUMNS = ("id", "past", "current")

    def parse(self, source):
        try:
            data_frame = pd.read_csv(
                source,
                names=list(self.COLUMNS),
                header=None,
            )
        except Exception as exc:
            raise CardListParseError(f"CSV 读取失败：{exc}") from exc

        if data_frame.empty:
            raise CardListParseError("CSV 内容为空。")

        for column in self.COLUMNS:
            converted = pd.to_numeric(data_frame[column], errors="coerce")
            if converted.isna().any():
                raise CardListParseError(f"CSV 的 {column} 列包含无效数字。")
            data_frame[column] = converted.astype(int)

        return data_frame.to_dict(orient="records")


if __name__ == "__main__":
    parser = CardListParser()
    card_list = parser.parse("card_list.csv")
    print(card_list)
