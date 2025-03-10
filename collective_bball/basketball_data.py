import polars as pl

from collective_bball.etl import load_data, clean_games_data
from collective_bball.player_data import PlayerData
from collective_bball.rapm_model import RAPMModel
from collective_bball.moneyline_model import BettingGames
from typing import Tuple, List

class BasketballData:
    def __init__(self, data_source: str, args: list):
        self.raw_games_data, self.tiers, self.bios = load_data(data_source)  # Read in from Excel (for now)
        self.games = None
        self.player_data = None
        self.player_games = None
        self.player_days = None
        self.days = None
        self.days_of_week = None
        self.args = args
        self.player_stats = None
        self.ratings = None
        self.best_lambda = None
        self.teammate_games = None
        self.opponent_games = None
        self.teammates = None
        self.opponents = None

    def clean_data(self):
        """Cleans raw game data into structured format."""
        self.games = clean_games_data(self.raw_games_data)

    def compute_player_stats(self):
        """Creates PlayerData object and computes player stats."""
        player_stats_obj = PlayerData(self.games, self.player_data)
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
            .join(self.bios, left_on="player", right_on="player", how="left")
    )

    def compute_spreads(self, betting_games: BettingGames):
        """Computes win probabilities for games."""
        self.games = betting_games.calculate_spreads(self.games, self.player_data)


    def compute_moneylines(self, betting_games: BettingGames):
        """Computes win probabilities for games."""
        self.games = betting_games.calculate_moneylines_log_reg(self.games)

    def assemble_player_data(self):
        """Combines games & player data into one row per player-game."""
        player_data_instance = PlayerData(self.games, self.player_data)
        self.player_games = player_data_instance.assemble_player_games()
        self.player_days = player_data_instance.assemble_player_days()
        self.player_data = player_data_instance.combine_player_stats_with_games_groupings()
        self.teammate_games, self.opponent_games, self.teammates, self.opponents = player_data_instance.calculate_teammate_opponent_pairings()


    def assemble_days_data(self):
        # TODO: Decide what we want to display from days and days of week dataframes
        self.days, self.days_of_week = self.compute_days(self.player_games, self.player_days)

    @staticmethod
    def compute_days(player_games: pl.DataFrame, player_days: pl.DataFrame) -> Tuple[pl.DataFrame, pl.DataFrame]:
        """Computes strength of day & fairness models."""

        days = player_days.group_by(["GameDate", "Day"]).agg(
            pl.count("GameDate").alias("NumPlayers"),
            pl.max('LastGameOfDay').alias("NumGames"),
            pl.mean('rating').round(3).alias("MeanRatingPlayers"),
            pl.max('LongestRunOnCourt'),
            pl.mean('LongestRunOnCourt').round(3).alias('AvgLongestRunOnCourt'),
            pl.max('LongestRunOnBench'),
            pl.mean('LongestRunOnBench').round(3).alias('AvgLongestRunOnBench'),
            (pl.col("Ws").gt(0).sum() / pl.count("GameDate")).round(3).alias("UniqueWinnersRate"),
            pl.std("Teammates_Avg").round(3).alias('AvgParityOfTeammates'),
            pl.std("Opps_Avg").round(3).alias('AvgParityOfTeams'),
        ).join((player_games.group_by(["GameDate", "Day"]).agg(
            pl.mean('rating').round(3).alias("MeanRatingPlayerGames"),
            pl.std('WinProb').round(3).alias("AvgParityOfWinProbs"),
            pl.col("Proj_Score_Diff").abs().std().round(3).alias("AvgParityOfSpread"),
            pl.col("Score_Difference").abs().std().round(3).alias("AvgParityOfScoreDiff"),
            pl.col("Score_Difference").abs().mean().round(3).alias("AvgScoreDiff")
        )),
            on=["GameDate", "Day"],
            how="inner"
        ).select(['GameDate', 'Day', 'NumPlayers', 'NumGames', 'MeanRatingPlayers', 'MeanRatingPlayerGames', 'AvgScoreDiff',
                  'LongestRunOnCourt', 'AvgLongestRunOnCourt', 'LongestRunOnBench', 'AvgLongestRunOnBench', 'UniqueWinnersRate',
                  'AvgParityOfTeammates', 'AvgParityOfTeams', 'AvgParityOfScoreDiff', 'AvgParityOfSpread', 'AvgParityOfWinProbs']).sort("GameDate", descending=True)

        days_of_week = (
            days.drop("GameDate")
            .group_by("Day")
            .agg(pl.all().mean().round(3))
        ).sort("MeanRatingPlayerGames", descending=True)

        return days, days_of_week
