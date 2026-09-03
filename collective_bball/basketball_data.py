import polars as pl
import duckdb

from collective_bball.etl import (
    load_data,
    clean_games_data,
    compute_clock,
    compute_starting_poss,
)
from collective_bball.player_data import PlayerData
from collective_bball.rapm_model import RAPMModel
from collective_bball.moneyline_model import BettingGames
from collective_bball.plots import Plots
from typing import Tuple, List, Union, IO

# Minimum games in a day to be eligible for that day's MVP or LVP, so one
# lucky or unlucky game cannot take the award.
MVP_MIN_GAMES = 3


class BasketballData:
    def __init__(self, data_source: Union[str, IO], args: list):
        self.raw_games_data, self.tiers = load_data(
            data_source
        )  # Read in from Excel (for now)
        self.games = None
        self.ingest_report = {}
        self.player_data = None
        self.player_games = None
        self.player_days = None
        self.days = None
        self.days_of_week = None
        self.args = args
        self.player_stats = None
        self.ratings = None
        self.ratings_by_date = None
        self.best_lambda = None
        self.teammate_games = None
        self.opponent_games = None
        self.teammates = None
        self.opponents = None
        self.plot_ratings = None

    def clean_data(self):
        """Cleans raw game data into structured format."""
        self.games, self.ingest_report = clean_games_data(self.raw_games_data)

    def compute_clock_and_starting_poss(self):
        """Uses logic to tease out whether clock was used and starting possession of a game."""
        self.games = compute_clock(self.games)
        self.games = compute_starting_poss(self.games)

    def compute_player_stats(self):
        """Creates PlayerData object and computes player stats."""
        player_stats_obj = PlayerData(self.games, self.player_data)
        self.player_stats = player_stats_obj.compute_stats()
        self.player_games = player_stats_obj.assemble_player_games()

    def compute_fatigue(self):
        """Creates two new variables to compute fatigue and warmth effects per game"""

        game_info_by_team = (
            self.player_games.group_by(pl.col(["game_date", "game_num", "team"]))
            .agg(
                (pl.sum("player_day_game_num") - 5).alias("team_total_games_played"),
                pl.sum("games_waited"),
                pl.sum("consecutive_games"),
            )
            .sort("game_date", "game_num", "team", descending=[True, True, True])
            .with_columns(
                [
                    pl.col("team_total_games_played").cast(pl.Int32),
                    pl.col("games_waited").cast(pl.Int32),
                    pl.col("consecutive_games").cast(pl.Int32),
                ]
            )
        )

        game_info_by_game = (
            game_info_by_team.pivot(
                "team",
                index=["game_date", "game_num"],
                values=["team_total_games_played", "games_waited", "consecutive_games"],
            )
            .with_columns(
                (
                    (
                        pl.col("team_total_games_played_A")
                        - pl.col("team_total_games_played_B")
                    )
                    / 5
                ).alias("total_games_played_diff"),
                ((pl.col("games_waited_A") - pl.col("games_waited_B")) / 5).alias(
                    "consecutive_games_waited_diff"
                ),
                (
                    (pl.col("consecutive_games_A") - pl.col("consecutive_games_B")) / 5
                ).alias("consecutive_games_played_diff"),
            )
            .with_columns(
                (pl.col("total_games_played_diff") ** 2).alias(
                    "total_games_played_diff_sq"
                ),
                (pl.col("consecutive_games_waited_diff") ** 2).alias(
                    "consecutive_games_waited_diff_sq"
                ),
                (pl.col("consecutive_games_played_diff") ** 2).alias(
                    "consecutive_games_played_diff_sq"
                ),
            )
        )

        self.games = self.games.join(game_info_by_game, on=["game_date", "game_num"])

        return self.games

    def compute_rapm(self, rapm_model: RAPMModel, date_to_filter=None):
        """Computes RAPM ratings and updates player data."""
        games_df = self.games.with_columns(
            pl.col("game_date")
            .str.strptime(pl.Date, "%Y-%m-%d")
            .alias("date_to_filter")
        )
        if date_to_filter:
            games_df = games_df.filter(
                pl.col("date_to_filter")
                <= pl.lit(date_to_filter).str.strptime(pl.Date, "%Y-%m-%d")
            )
        self.ratings, self.best_lambda = rapm_model.run_rapm(
            games_df, self.tiers, self.args
        )

    def compute_time_centered_ratings(self, rapm_model: RAPMModel):
        """Per-game-day ratings, so a historical game keeps its own context.

        The model works in tier space: players under the games threshold are
        substituted for their tier before fitting, so a coefficient comes back
        for "Tier3" and not for them. This expands that back out, exactly as
        merge_player_data does for the career rating -- own coefficient if the
        player earned one, otherwise their tier's.
        """
        raw = rapm_model.run_time_centered(self.games, self.tiers, self.args)

        own = raw.rename({"rating": "own_rating"})
        via_tier = raw.rename({"player": "tier", "rating": "tier_rating"})

        # Every real player on every game day, then coalesce.
        grid = self.tiers.select(["player", "tier"]).join(
            raw.select("game_date").unique(), how="cross"
        )
        self.ratings_by_date = (
            grid.join(own, on=["player", "game_date"], how="left")
            .join(via_tier, on=["tier", "game_date"], how="left")
            .with_columns(
                pl.col("own_rating").fill_null(pl.col("tier_rating")).alias("rating")
            )
            .drop_nulls("rating")
            .select(["game_date", "player", pl.col("rating").round(4)])
        )
        return self.ratings_by_date

    def merge_player_data(self):
        """Merges stats and RAPM ratings into a single DataFrame."""
        if self.player_stats is None or self.ratings is None:
            raise ValueError(
                "Both player stats and RAPM ratings must exist before merging!"
            )
        self.player_data = (
            self.player_stats.join(
                self.ratings, left_on="player", right_on="player", how="left"
            )
            .join(self.tiers, left_on="player", right_on="player", how="left")
            .join(self.ratings, left_on="tier", right_on="player", how="left")
            .with_columns(pl.col("rating").fill_null(pl.col("rating_right")))
            .with_columns(
                (pl.col("rating") == pl.col("rating_right"))
                .cast(pl.Int64)
                .fill_null(0)
                .alias("tiered_rating")
            )
            .sort("rating", "wins", "win_pct", descending=[True, True, True])
            .drop(["uncommon", "tier", "description", "rating_right"])
        )

    def compute_spreads(self, betting_games: BettingGames):
        """Computes win probabilities for games.

        Fed the per-date ratings, not the career ones: a game's spread should
        describe the teams that actually took the floor that night, and stay
        put once it has been played.
        """
        self.games = betting_games.calculate_spreads(self.games, self.ratings_by_date)

    def compute_moneylines(self, betting_games: BettingGames):
        """Computes win probabilities for games."""
        self.games = betting_games.calculate_moneylines_log_reg(self.games)

    @staticmethod
    def add_role_ranks(player_games: pl.DataFrame) -> pl.DataFrame:
        """Where each player sat in the pecking order for a given game.

        `team_rank` 1-5 is their rating's rank among their own five;
        `court_rank` 1-10 is the rank among everyone on the floor.

        Ranking is "min" (competition) style, so genuine ties share the better
        rank and the next rank is skipped — two players tied at the top are
        both 1st and nobody is 2nd. Ties are rare (about 4% of team-games) and
        come almost entirely from players who share a tier rating, so forcing
        an arbitrary winner would invent precision the model doesn't have.
        """
        game = ["game_date", "game_num"]
        return player_games.with_columns(
            pl.col("rating")
            .rank(method="min", descending=True)
            .over(game + ["team"])
            .cast(pl.Int32)
            .alias("team_rank"),
            pl.col("rating")
            .rank(method="min", descending=True)
            .over(game)
            .cast(pl.Int32)
            .alias("court_rank"),
        )

    def assemble_player_data(self):
        """Combines games & player data into one row per player-game."""
        player_data_instance = PlayerData(
            self.games, self.player_data, self.ratings_by_date
        )
        self.player_games = self.add_role_ranks(
            player_data_instance.add_ratings_to_player_games()
        )
        self.player_days = player_data_instance.assemble_player_days()
        self.player_data = (
            player_data_instance.combine_player_stats_with_games_groupings()
        )
        self.teammate_games, self.opponent_games, self.teammates, self.opponents = (
            player_data_instance.calculate_teammate_opponent_pairings()
        )

    def assemble_days_data(self):
        self.days, self.days_of_week = self.compute_days(
            self.player_games, self.player_days
        )
        # Depends on `days`, so it has to follow that computation rather than
        # sit with the rest of the per-player aggregation.
        self.player_data = self.add_mvp_lvp_counts(self.player_data, self.days)

    @staticmethod
    def add_mvp_lvp_counts(
        player_data: pl.DataFrame, days: pl.DataFrame
    ) -> pl.DataFrame:
        """How often each player took the day's MVP or LVP, as a count and a
        rate over the days they played."""
        mvps = (
            days.filter(pl.col("mvp").is_not_null())
            .group_by("mvp")
            .agg(pl.len().alias("mvps"))
            .rename({"mvp": "player"})
        )
        lvps = (
            days.filter(pl.col("lvp").is_not_null())
            .group_by("lvp")
            .agg(pl.len().alias("lvps"))
            .rename({"lvp": "player"})
        )

        combined = (
            player_data.join(mvps, on="player", how="left")
            .join(lvps, on="player", how="left")
            .with_columns(
                pl.col("mvps").fill_null(0).cast(pl.Int32),
                pl.col("lvps").fill_null(0).cast(pl.Int32),
            )
            .with_columns(
                (pl.col("mvps") / pl.col("days_played")).round(4).alias("mvp_pct"),
                (pl.col("lvps") / pl.col("days_played")).round(4).alias("lvp_pct"),
            )
        )

        # Slot the four new columns in after "% better teammates", where Jason
        # wants them, instead of appending to the end.
        added = ["mvps", "lvps", "mvp_pct", "lvp_pct"]
        rest = [c for c in combined.columns if c not in added]
        anchor = "pct_games_better_teammates"
        at = rest.index(anchor) + 1 if anchor in rest else len(rest)
        return combined.select(rest[:at] + added + rest[at:])

    def write_to_db(self, conn, date_to_filter=None):
        """Snapshot the current ratings under the workbook's latest game date.

        DO UPDATE, not DO NOTHING. Games get logged over the couple of hours a
        run is happening, so a rebuild that fires mid-session would otherwise
        pin that day's snapshot to a partial slate and never revise it — one
        game in, and the ratings-over-time chart carries that forever.

        Overwriting cannot corrupt older history: every rebuild writes exactly
        one date, the newest in the workbook, so earlier snapshots are never
        touched. Only the day still in progress moves, which is the point.
        """
        ratings_df = self.ratings.with_columns(
            pl.lit(
                date_to_filter or self.games["game_date"].unique().sort().last()
            ).alias("date")
        ).to_pandas()
        conn.execute(
            "INSERT INTO ratings BY NAME SELECT * FROM ratings_df "
            "ON CONFLICT(player, date) DO UPDATE SET rating = EXCLUDED.rating"
        )

    @staticmethod
    def compute_day_mvp_lvp(player_days: pl.DataFrame) -> pl.DataFrame:
        """Best and worst performer on each day, by result versus expectation.

        Requires at least three games so a single lucky or unlucky game cannot
        take the award. Ties break alphabetically, which is arbitrary but
        stable across rebuilds.
        """
        eligible = player_days.filter(pl.col("games_played") >= MVP_MIN_GAMES).sort(
            ["game_date", "result_vs_expectation_avg", "player"],
            descending=[False, True, False],
        )

        return (
            eligible.group_by("game_date")
            .agg(
                pl.col("player").first().alias("mvp"),
                pl.col("result_vs_expectation_avg").first().alias("mvp_gospel"),
                pl.col("player").last().alias("lvp"),
                pl.col("result_vs_expectation_avg").last().alias("lvp_gospel"),
            )
            .with_columns(
                pl.col("mvp_gospel").round(3),
                pl.col("lvp_gospel").round(3),
            )
        )

    @staticmethod
    def compute_days(
        player_games: pl.DataFrame, player_days: pl.DataFrame
    ) -> Tuple[pl.DataFrame, pl.DataFrame]:
        """Computes strength of day & fairness models."""

        days = (
            player_days.group_by(["game_date", "day"])
            .agg(
                pl.count("game_date").alias("num_players"),
                pl.sum("resident").alias("residents"),
                pl.mean("resident").round(3).alias("resident_rate"),
                pl.max("last_game_of_day").alias("num_games"),
                pl.mean("rating").round(3).alias("mean_rating_players"),
                pl.max("longest_run_on_court"),
                pl.mean("longest_run_on_court")
                .round(3)
                .alias("avg_longest_run_on_court"),
                pl.max("longest_run_on_bench"),
                pl.mean("longest_run_on_bench")
                .round(3)
                .alias("avg_longest_run_on_bench"),
                (pl.col("wins").gt(0).sum() / pl.count("game_date"))
                .round(3)
                .alias("unique_winners_rate"),
                pl.std("teammates_avg").round(3).alias("avg_parity_of_teammates"),
                pl.std("opps_avg").round(3).alias("avg_parity_of_teams"),
            )
            .join(
                (
                    player_games.group_by(["game_date", "day"]).agg(
                        pl.mean("rating").round(3).alias("mean_rating_player_games"),
                        pl.std("win_prob").round(3).alias("avg_parity_of_win_probs"),
                        pl.col("proj_score_diff")
                        .abs()
                        .std()
                        .round(3)
                        .alias("avg_parity_of_spread"),
                        pl.col("score_diff")
                        .abs()
                        .std()
                        .round(3)
                        .alias("avg_parity_of_score_diff"),
                        pl.col("score_diff")
                        .abs()
                        .mean()
                        .round(3)
                        .alias("avg_score_diff"),
                    )
                ),
                on=["game_date", "day"],
                how="inner",
            )
            .join(
                BasketballData.compute_day_mvp_lvp(player_days),
                on="game_date",
                how="left",
            )
            .select(
                [
                    "game_date",
                    "day",
                    "num_players",
                    "residents",
                    "resident_rate",
                    "num_games",
                    "mvp",
                    "mvp_gospel",
                    "lvp",
                    "lvp_gospel",
                    "mean_rating_players",
                    "mean_rating_player_games",
                    "avg_score_diff",
                    "longest_run_on_court",
                    "avg_longest_run_on_court",
                    "longest_run_on_bench",
                    "avg_longest_run_on_bench",
                    "unique_winners_rate",
                    "avg_parity_of_teammates",
                    "avg_parity_of_teams",
                    "avg_parity_of_score_diff",
                    "avg_parity_of_spread",
                    "avg_parity_of_win_probs",
                ]
            )
            .sort("game_date", descending=True)
        )

        # MVP/LVP are player names, so they are dropped before averaging rather
        # than fed to mean().
        days_of_week = (
            days.drop("game_date", "mvp", "lvp", "mvp_gospel", "lvp_gospel")
            .group_by("day")
            .agg(pl.all().mean().round(3))
        ).sort("mean_rating_player_games", descending=True)

        return days, days_of_week

    def plot_things(self, plots: Plots):

        self.plot_ratings = plots.plot_ratings_time()
        self.plot_rapm_apm = plots.plot_rapm_vs_apm(player_data=self.player_data)
