import pandas as pd

class CardListParser:
    def __init__(self, file_path):
        self.file_path = file_path

    def parse(self):
        try:
            df = pd.read_csv(self.file_path, names=['id', 'past', 'current'], header=None)

            for col in ['id', 'past', 'current']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
            res = df.to_dict(orient='records')
            for card in res:
                for key in ['id', 'past', 'current']:
                    if card[key] is None:
                        raise ValueError(f"Card with id {card.get('id', 'unknown')} has invalid value in column '{key}'.")
            return res
        except Exception as e:
            print(f"Error parsing card list: {e}")
            return []
        
if __name__ == "__main__":
    parser = CardListParser("card_list.csv")
    card_list = parser.parse()
    print(card_list)