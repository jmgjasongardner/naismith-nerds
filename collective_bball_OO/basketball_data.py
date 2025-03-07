import pandas as pd
from etl import load_data, clean_games_data
from player_data import PlayerData
from rapm_model import RAPMModel
from moneyline_model import MoneylineModel

class BasketballData:
    def __init__(self, data_source: str, args: list):
        self.raw_games_data, self.tiers, self.bios = load_data(data_source)  # Read in from Excel (for now)
        self.games = None
        self.player_data = None
        self.player_games = None
        self.days = None
        self.args = args

    def clean_data(self):
        """Cleans raw game data into structured format."""
        self.games = clean_games_data(self.raw_games_data)

    def compute_player_stats(self):
        """Creates PlayerData object and computes player stats."""
        player_stats_obj = PlayerData(self.games)
        self.player_stats = player_stats_obj.compute_stats()

    def compute_rapm(self, rapm_model: RAPMModel):
        """Computes RAPM ratings and updates player data."""
        self.ratings = rapm_model.run_rapm(self.games, self.tiers, self.args)

    def merge_player_data(self):
        """Merges stats and RAPM ratings into a single DataFrame."""
        if self.player_stats is None or self.ratings is None:
            raise ValueError("Both player stats and RAPM ratings must exist before merging!")
        self.player_data = self.player_stats.join(self.ratings, on="Player", how="left")

    def compute_moneylines(self, moneyline_model: MoneylineModel):
        """Computes win probabilities for games."""
        self.games = moneyline_model.run(self.games, self.player_data)

    def assemble_final_data(self):
        """Combines games & player data into final tables."""
        self.player_games = self.games.merge(self.player_data, on="Player", how="left")
        self.days = self.compute_days(self.games, self.player_games)

    @staticmethod
    def compute_days(games: pd.DataFrame, player_games: pd.DataFrame) -> pd.DataFrame:
        """Computes strength of day & fairness models."""
        return games  # Placeholder for now
