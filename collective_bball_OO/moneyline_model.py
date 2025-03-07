from sklearn.linear_model import LogisticRegression
import polars as pl

class MoneylineModel:
    def __init__(self):
        self.model = LogisticRegression()

    def run(self, games: pl.DataFrame, player_data: pl.DataFrame) -> pl.DataFrame:
        """Trains logistic regression and computes win probabilities."""
        X, y = self.preprocess_data(games)
        self.model.fit(X, y)
        games["Win_Prob_A"] = self.model.predict_proba(X)[:, 1]
        return games

    @staticmethod
    def preprocess_data(games: pl.DataFrame):
        """Prepares features for logistic regression."""
        return games[['A_Quality', 'B_Quality']], games['Winner'].map({'A': 1, 'B': 0})
