import polars as pl

from etl import load_data, clean_games_data
from player_data import PlayerData
from rapm_model import RAPMModel
from moneyline_model import BettingGames
from utils import util_code

class BasketballData:
    def __init__(self, data_source: str, args: list):
        self.raw_games_data, self.tiers, self.bios = load_data(data_source)  # Read in from Excel (for now)
        self.games = None
        self.player_data = None
        self.player_games = None
        self.days = None
        self.args = args
        self.player_stats = None
        self.ratings = None
        self.best_lambda = None

    def clean_data(self):
        """Cleans raw game data into structured format."""
        self.games = clean_games_data(self.raw_games_data)

    def compute_player_stats(self):
        """Creates PlayerData object and computes player stats."""
        player_stats_obj = PlayerData(self.games)
        self.player_stats = player_stats_obj.compute_stats()

    def compute_rapm(self, rapm_model: RAPMModel):
        """Computes RAPM ratings and updates player data."""
        self.ratings, self.best_lambda = rapm_model.run_rapm(self.games, self.tiers, self.args)

    def merge_player_data(self):
        """Merges stats and RAPM ratings into a single DataFrame."""
        if self.player_stats is None or self.ratings is None:
            raise ValueError("Both player stats and RAPM ratings must exist before merging!")
        self.player_data = (
            self.player_stats.join(self.ratings, left_on="player", right_on="player", how="left")
            .join(self.tiers, left_on="player", right_on="player", how="left")
            .join(self.ratings, left_on="tier", right_on="player", how="left")
            .with_columns(pl.col("rating").fill_null(pl.col("rating_right")))
            .with_columns((pl.col("rating") == pl.col("rating_right")).cast(pl.Int64).fill_null(0).alias("tiered_rating"))
            .sort("rating", "wins", "win_pct", descending=[True, True, True])
            .drop(["uncommon", "tier", "description", "rating_right"])
    )

    def compute_spreads(self, betting_games: BettingGames):
        """Computes win probabilities for games."""
        self.games = betting_games.calculate_spreads(self.games, self.player_data)


    def compute_moneylines(self, betting_games: BettingGames):
        """Computes win probabilities for games."""
        self.games = betting_games.calculate_moneylines_log_reg(self.games)

    def assemble_final_data(self):
        """Combines games & player data into final tables."""
        key_cols = [
            "Date", "GameDate", "GameNum", "Winner", "A_SCORE", "B_SCORE", "A_Quality", "B_Quality",
            "Spread", "Score_Difference", "Difference_From_Spread", "Moneyline", "A_Win_Prob"
        ]

        # Add teammates and opponents as list columns BEFORE unpivoting
        df_prepped = self.games.with_columns([
            pl.concat_list([pl.col(f"A{i}") for i in range(1, 6)]).alias("A_Teammates"),
            pl.concat_list([pl.col(f"B{i}") for i in range(1, 6)]).alias("B_Teammates"),
            pl.concat_list([pl.col(f"B{i}") for i in range(1, 6)]).alias("A_Opponents"),
            pl.concat_list([pl.col(f"A{i}") for i in range(1, 6)]).alias("B_Opponents"),
        ])

        # Unpivot to transform A1-A5 and B1-B5 into a single "Player" column
        df_long = (
            df_prepped.unpivot(
                index=key_cols + ["A_Teammates", "B_Teammates", "A_Opponents", "B_Opponents"],
                on=util_code.player_columns,
                variable_name="PlayerRole",
                value_name="Player"
            )
            .with_columns([
                # Assign team
                pl.when(pl.col("PlayerRole").str.starts_with("A"))
                .then(pl.lit("A"))
                .otherwise(pl.lit("B"))
                .alias("Team"),

                # Assign teammates and opponents based on team
                pl.when(pl.col("PlayerRole").str.starts_with("A"))
                .then(pl.col("A_Teammates"))
                .otherwise(pl.col("B_Teammates"))
                .alias("Teammates"),

                pl.when(pl.col("PlayerRole").str.starts_with("A"))
                .then(pl.col("A_Opponents"))
                .otherwise(pl.col("B_Opponents"))
                .alias("Opponents")])
        ).with_columns(
            pl.struct(["Teammates", "Player"]).map_elements(
                lambda x: [t for t in x["Teammates"] if t != x["Player"]]
            ).alias("Teammates")
        )
        df_long = df_long.with_columns([
                # Assign team-specific values
                pl.when(pl.col("Team") == "A").then(pl.col("A_SCORE")).otherwise(pl.col("B_SCORE")).alias("Team_Score"),
                pl.when(pl.col("Team") == "A").then(pl.col("B_SCORE")).otherwise(pl.col("A_SCORE")).alias("Opp_Score"),
                pl.when(pl.col("Team") == "A").then(-pl.col("Score_Difference")).otherwise(pl.col("Score_Difference")).alias("Score_Difference"),
                pl.when(pl.col("Team") == "A").then(-pl.col("Difference_From_Spread")).otherwise(pl.col("Difference_From_Spread")).alias("Difference_From_Spread"),
                pl.when(pl.col("Team") == "A").then(pl.col("A_Quality")).otherwise(pl.col("B_Quality")).alias(
                    "Team_Quality"),
                pl.when(pl.col("Team") == "A").then(pl.col("B_Quality")).otherwise(pl.col("A_Quality")).alias(
                    "Opp_Quality"),
                pl.when(pl.col("Team") == "A").then(-pl.col("Spread")).otherwise(pl.col("Spread")).alias(
                    "Proj_Score_Diff"),
                pl.when(pl.col("Team") == "A").then(pl.col("A_Win_Prob")).otherwise(1 - pl.col("A_Win_Prob")).alias(
                    "WinProb"),
                pl.when(pl.col("Team") == "A").then(pl.col("Moneyline")).otherwise(-pl.col("Moneyline")).alias(
                    "Moneyline"),
                pl.when(pl.col("Team") == pl.col("Winner")).then(pl.lit(1)).otherwise(pl.lit(0)).alias("Winner"),
            ]).drop(["PlayerRole", "A_Teammates", "B_Teammates", "A_Opponents", "B_Opponents"])

        # Explode teammates and opponents into separate columns (if needed)
        self.player_games = df_long.with_columns([
                                            pl.col("Teammates").list.get(i).alias(f"T{i + 1}") for i in range(4)
                                        ] + [
                                            pl.col("Opponents").list.get(i).alias(f"O{i + 1}") for i in range(5)
                                        ]).drop(["Teammates", "Opponents", 'A_SCORE', 'B_SCORE',
       'A_Quality', 'B_Quality', 'Spread', 'A_Win_Prob']).select(
            ['Date', 'GameDate', 'GameNum', 'Player', 'Team', 'Team_Score', 'Opp_Score', 'Winner', 'Score_Difference',
             'WinProb', 'Moneyline', 'Proj_Score_Diff', 'Difference_From_Spread', 'Team_Quality', 'Opp_Quality',
             'T1', 'T2', 'T3', 'T4', 'O1', 'O2', 'O3', 'O4', 'O5']
        )
        self.days = self.compute_days(self.games, self.player_games)

    @staticmethod
    def compute_days(games: pl.DataFrame, player_games: pl.DataFrame) -> pl.DataFrame:
        """Computes strength of day & fairness models."""
        return games  # Placeholder for now
