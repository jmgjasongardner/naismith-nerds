import polars as pl
from collective_bball.utils import util_code


class PlayerData:
    def __init__(self, games: pl.DataFrame, player_data: pl.DataFrame):
        self.games = games
        self.player_data = player_data
        self.player_stats = None
        self.player_games = None
        self.player_days = None
        self.teammate_games = None
        self.opponent_games = None
        self.teammates = None
        self.opponents = None

    def compute_stats(self) -> pl.DataFrame:
        """Extracts player stats from games."""
        team_cols = util_code.player_columns
        id_cols = ["game_date", "game_num", "a_score", "b_score", "winner"]

        players = (
            self.games.select(id_cols + team_cols)
            .unpivot(index=id_cols)
            .with_columns(
                pl.col("variable").str.extract(r"([AB])", 1).alias("team"),
                pl.col("value").alias("player"),
            )
            .drop(["value", "variable"])
            .with_columns(
                pl.when(pl.col("team") == "A")
                .then(pl.col("a_score"))
                .otherwise(pl.col("b_score"))
                .alias("team_score"),
                pl.when(pl.col("team") == "A")
                .then(pl.col("b_score"))
                .otherwise(pl.col("a_score"))
                .alias("opponent_score"),
                (pl.col("team") == pl.col("winner")).cast(pl.Int8).alias("game_won"),
            )
            .with_columns(
                (pl.col("team_score") - pl.col("opponent_score")).alias("score_diff")
            )
        )

        self.player_stats = (
            players.group_by("player")
            .agg(
                [
                    pl.count("player").alias("games_played"),
                    pl.n_unique("game_date").alias("days_played"),
                    pl.sum("game_won").alias("wins"),
                    (pl.count("player") - pl.sum("game_won")).alias("losses"),
                    (pl.sum("game_won") / pl.count("player")).round(3).alias("win_pct"),
                    pl.mean("score_diff").round(3).alias("avg_score_diff"),
                ]
            )
            .sort("wins", "losses", "avg_score_diff", descending=[True, False, True])
        )

        return self.player_stats

    def assemble_player_games(self):
        """Combines games & player data into final tables."""
        key_cols = [
            "game_date",
            "game_num",
            "day",
            "winner",
            "a_score",
            "b_score",
            "a_quality",
            "b_quality",
            "spread",
            "score_diff",
            "diff_from_spread",
            "moneyline",
            "a_win_prob",
        ]

        # Add teammates and opponents as list columns BEFORE unpivoting
        df_prepped = self.games.with_columns(
            [
                pl.concat_list([pl.col(f"A{i}") for i in range(1, 6)]).alias(
                    "a_teammates"
                ),
                pl.concat_list([pl.col(f"B{i}") for i in range(1, 6)]).alias(
                    "b_teammates"
                ),
                pl.concat_list([pl.col(f"B{i}") for i in range(1, 6)]).alias(
                    "a_opponents"
                ),
                pl.concat_list([pl.col(f"A{i}") for i in range(1, 6)]).alias(
                    "b_opponents"
                ),
            ]
        )

        # Unpivot to transform A1-A5 and B1-B5 into a single "player" column
        df_long = (
            df_prepped.unpivot(
                index=key_cols
                + ["a_teammates", "b_teammates", "a_opponents", "b_opponents"],
                on=util_code.player_columns,
                variable_name="player_role",
                value_name="player",
            ).with_columns(
                [
                    # Assign team
                    pl.when(pl.col("player_role").str.starts_with("A"))
                    .then(pl.lit("A"))
                    .otherwise(pl.lit("B"))
                    .alias("team"),
                    # Assign teammates and opponents based on team
                    pl.when(pl.col("player_role").str.starts_with("A"))
                    .then(pl.col("a_teammates"))
                    .otherwise(pl.col("b_teammates"))
                    .alias("teammates"),
                    pl.when(pl.col("player_role").str.starts_with("A"))
                    .then(pl.col("a_opponents"))
                    .otherwise(pl.col("b_opponents"))
                    .alias("opponents"),
                ]
            )
        ).with_columns(
            pl.struct(["teammates", "player"])
            .map_elements(
                lambda x: [t for t in x["teammates"] if t != x["player"]],
                return_dtype=pl.List(pl.Utf8),
            )
            .alias("teammates")
        )
        df_long = (
            df_long.with_columns(
                [
                    # Assign team-specific values
                    pl.when(pl.col("team") == "A")
                    .then(pl.col("a_score"))
                    .otherwise(pl.col("b_score"))
                    .alias("team_score"),
                    pl.when(pl.col("team") == "A")
                    .then(pl.col("b_score"))
                    .otherwise(pl.col("a_score"))
                    .alias("opp_score"),
                    pl.when(pl.col("team") == "A")
                    .then(-pl.col("score_diff"))
                    .otherwise(pl.col("score_diff"))
                    .alias("score_diff"),
                    pl.when(pl.col("team") == "A")
                    .then(-pl.col("diff_from_spread"))
                    .otherwise(pl.col("diff_from_spread"))
                    .alias("diff_from_spread"),
                    pl.when(pl.col("team") == "A")
                    .then(pl.col("a_quality"))
                    .otherwise(pl.col("b_quality"))
                    .alias("team_quality"),
                    pl.when(pl.col("team") == "A")
                    .then(pl.col("b_quality"))
                    .otherwise(pl.col("a_quality"))
                    .alias("opp_quality"),
                    pl.when(pl.col("team") == "A")
                    .then(-pl.col("spread"))
                    .otherwise(pl.col("spread"))
                    .alias("proj_score_diff"),
                    pl.when(pl.col("team") == "A")
                    .then(pl.col("a_win_prob"))
                    .otherwise(1 - pl.col("a_win_prob"))
                    .alias("win_prob"),
                    pl.when(pl.col("team") == "A")
                    .then(pl.col("moneyline"))
                    .otherwise(-pl.col("moneyline"))
                    .alias("moneyline"),
                    pl.when(pl.col("team") == pl.col("winner"))
                    .then(pl.lit(1))
                    .otherwise(pl.lit(0))
                    .alias("winner"),
                ]
            )
            .drop(
                [
                    "player_role",
                    "a_teammates",
                    "b_teammates",
                    "a_opponents",
                    "b_opponents",
                ]
            )
            .join(
                self.player_data.select(["player", "rating"]),
                left_on="player",
                right_on="player",
                how="left",
            )
            .with_columns(
                (pl.col("team_quality") - pl.col("rating"))
                .round(3)
                .alias("teammate_quality")
            )
            .with_columns(
                (pl.col("teammate_quality") - pl.col("opp_quality"))
                .round(3)
                .alias("other_9_players_quality_diff")
            )
        )

        # Explode teammates and opponents into separate columns (if needed)
        self.player_games = (
            df_long.with_columns(
                [pl.col("teammates").list.get(i).alias(f"T{i + 1}") for i in range(4)]
                + [pl.col("opponents").list.get(i).alias(f"O{i + 1}") for i in range(5)]
            )
            .drop(
                [
                    "teammates",
                    "opponents",
                    "a_score",
                    "b_score",
                    "a_quality",
                    "b_quality",
                    "spread",
                    "a_win_prob",
                ]
            )
            .select(
                [
                    "game_date",
                    "game_num",
                    "day",
                    "player",
                    "rating",
                    "team",
                    "team_score",
                    "opp_score",
                    "winner",
                    "score_diff",
                    "win_prob",
                    "moneyline",
                    "proj_score_diff",
                    "diff_from_spread",
                    "team_quality",
                    "teammate_quality",
                    "opp_quality",
                    "other_9_players_quality_diff",
                    "T1",
                    "T2",
                    "T3",
                    "T4",
                    "O1",
                    "O2",
                    "O3",
                    "O4",
                    "O5",
                ]
            )
            .sort(["player", "game_date", "game_num"])
            .with_columns(
                [
                    # player_game_num: Count up within each player, ordered by game_date -> game_num
                    pl.col("game_num")
                    .cum_count()
                    .over("player")
                    .alias("player_game_num"),
                    # playerwinNum: Running total of wins per player, ordered by game_date -> game_num
                    pl.col("winner").cum_sum().over("player").alias("player_win_num"),
                    # playerLossNum: Total games played - wins
                    (
                        pl.col("game_num").cum_count().over("player")
                        - pl.col("winner").cum_sum().over("player")
                    ).alias("player_loss_num"),
                    # playerdaygame_num: Count up within each (player, game_date), ordered by game_num
                    pl.col("game_num")
                    .cum_count()
                    .over(["player", "game_date"])
                    .alias("player_day_game_num"),
                    # Identify first_game (1 if first row for player, 0 otherwise)
                    (
                        pl.col("game_num")
                        == pl.col("game_num").min().over(["player", "game_date"])
                    )
                    .cast(pl.Int8)
                    .alias("first_game_of_day"),
                    (
                        pl.col("game_num")
                        == pl.col("game_num").max().over(["player", "game_date"])
                    )
                    .cast(pl.Int8)
                    .alias("last_game_of_day"),
                    (pl.col("game_num") == pl.col("game_num").min().over(["game_date"]))
                    .cast(pl.Int8)
                    .alias("played_first_game"),
                    (pl.col("game_num") == pl.col("game_num").max().over(["game_date"]))
                    .cast(pl.Int8)
                    .alias("played_last_game"),
                ]
            )
            .with_columns(
                [
                    # Calculate games_waited (days since last appearance)
                    (
                        pl.col("game_num")
                        - pl.col("game_num").shift(1).over(["player", "game_date"])
                        - 1
                    )
                    .fill_null(0)
                    .alias("games_waited"),
                    # Identify resets: Either a new game_date or a missing game_num
                    (
                        (
                            pl.col("game_num")
                            - pl.col("game_num").shift(1).over(["player", "game_date"])
                            > 1
                        )
                        | (
                            pl.col("game_date")
                            != pl.col("game_date")
                            .shift(1)
                            .over(["player", "game_date"])
                        )
                    )
                    .fill_null(True)  # First row should be considered a reset
                    .cast(pl.Int8)
                    .alias("GameReset"),
                ]
            )
            .with_columns(
                [
                    # Initialize consecutive_games with 0 and mark the first game or reset points
                    pl.when(pl.col("GameReset") == 1)
                    .then(pl.lit(0))
                    .otherwise(pl.lit(1))
                    .alias("consecutive_gamesInitial")
                ]
            )
            .with_columns(
                [
                    # Calculate consecutive_games based on resets
                    pl.when(pl.col("GameReset") == 1)
                    .then(pl.lit(0))
                    .otherwise(
                        pl.col("consecutive_gamesInitial")
                        .cum_sum()
                        .over(["player", "game_date"])
                    )
                    .alias("consecutive_games")
                ]
            )
            .drop(["GameReset", "consecutive_gamesInitial"])
        )
        return self.player_games

    def assemble_player_days(self):
        self.player_days = (
            self.player_games.group_by(["player", "game_date", "day", "rating"])
            .agg(
                pl.count("player").alias("games_played"),
                pl.sum("winner").alias("wins"),
                (pl.count("player") - pl.sum("winner")).alias("losses"),
                (pl.sum("winner") / pl.count("player")).round(3).alias("win_pct"),
                pl.mean("win_prob").round(3).alias("exp_win_pct"),
                pl.mean("proj_score_diff").round(3),
                pl.mean("teammate_quality").round(3).alias("teammates_avg"),
                pl.mean("opp_quality").round(3).alias("opps_avg"),
                pl.mean("other_9_players_quality_diff")
                .round(3)
                .alias("other_9_player_avg"),
                pl.sum("played_first_game"),
                pl.sum("played_last_game"),
                pl.min("game_num").alias("first_game_of_day"),
                pl.max("game_num").alias("last_game_of_day"),
                pl.max("consecutive_games").alias("longest_run_on_court"),
                pl.max("games_waited").alias("longest_run_on_bench"),
            )
            .sort(
                "game_date",
                "first_game_of_day",
                "player",
                descending=[True, False, False],
            )
        )
        return self.player_days

    def combine_player_stats_with_games_groupings(self):
        self.player_data = self.player_data.join(
            self.player_games.group_by(["player"]).agg(
                pl.sum("win_prob").round(3).alias("expected_wins"),
                (pl.sum("win_prob") / pl.count("player"))
                .round(3)
                .alias("expected_win_pct"),
                pl.mean("proj_score_diff").round(3).alias("proj_score_diff"),
                (pl.count("player") / len(self.games))
                .round(3)
                .alias("pct_total_games_played"),
                (pl.n_unique("game_date") / len(self.games["game_date"].unique()))
                .round(3)
                .alias("pct_total_days_played"),
                pl.max("game_date").alias("most_recent_game"),
                pl.mean("teammate_quality").round(3),
                pl.mean("team_quality").round(3),
                pl.mean("opp_quality").round(3),
                pl.col("teammate_quality")
                .gt(0)
                .mean()
                .round(3)
                .alias("pct_positive_teammates"),
                pl.col("opp_quality")
                .gt(0)
                .mean()
                .round(3)
                .alias("pct_positive_opponents"),
                pl.col("proj_score_diff")
                .gt(0)
                .mean()
                .round(3)
                .alias("pct_games_favorite"),
                (pl.col("opp_quality") < pl.col("teammate_quality"))
                .mean()
                .round(3)
                .alias("pct_games_better_teammates"),
                pl.mean("other_9_players_quality_diff").round(3),
            ),
            left_on="player",
            right_on="player",
            how="inner",
        ).join(
            self.player_days.group_by(["player"]).agg(
                pl.mean("games_played").round(3).alias("games_played_per_day"),
                (pl.sum("played_first_game") / pl.count("player"))
                .round(3)
                .alias("first_game_of_day_rate"),
                (pl.sum("played_last_game") / pl.count("player"))
                .round(3)
                .alias("last_game_of_day_rate"),
                (
                    (pl.when(pl.col("day") == "Mon").then(1).otherwise(0)).sum()
                    / self.games.filter(pl.col("day") == "Mon")["game_date"].n_unique()
                )
                .round(3)
                .alias("mon_rate"),
                (
                    (pl.when(pl.col("day") == "Wed").then(1).otherwise(0)).sum()
                    / self.games.filter(pl.col("day") == "Wed")["game_date"].n_unique()
                )
                .round(3)
                .alias("wed_rate"),
                (
                    (pl.when(pl.col("day") == "Sat").then(1).otherwise(0)).sum()
                    / self.games.filter(pl.col("day") == "Sat")["game_date"].n_unique()
                )
                .round(3)
                .alias("sat_rate"),
            ),
            left_on="player",
            right_on="player",
            how="inner",
        )

        return self.player_data

    def calculate_teammate_opponent_pairings(self):
        key_cols = [
            "game_date",
            "game_num",
            "day",
            "player",
            "rating",
            "team",
            "team_score",
            "opp_score",
            "winner",
            "score_diff",
            "win_prob",
            "moneyline",
            "proj_score_diff",
            "diff_from_spread",
            "team_quality",
            "teammate_quality",
            "opp_quality",
            "other_9_players_quality_diff",
        ]

        # Unpivot to transform A1-A5 and B1-B5 into a single "player" column
        self.teammate_games = (
            self.player_games.unpivot(
                index=key_cols,
                on=[f"T{i}" for i in range(1, 5)],
                variable_name="player_role",
                value_name="teammate",
            )
            .drop("player_role")
            .join(
                self.player_data.select(["player", "rating"]),
                left_on="teammate",
                right_on="player",
                suffix="_teammate",
            )
            .with_columns(
                (pl.col("teammate_quality") - pl.col("rating_teammate")).round(3),
                (pl.col("other_9_players_quality_diff") - pl.col("rating_teammate"))
                .round(3)
                .alias("other_8_players_quality_diff"),
            )
            .drop("other_9_players_quality_diff")
        )

        self.opponent_games = (
            self.player_games.unpivot(
                index=key_cols,
                on=[f"O{i}" for i in range(1, 6)],
                variable_name="player_role",
                value_name="opponent",
            )
            .drop("player_role")
            .join(
                self.player_data.select(["player", "rating"]),
                left_on="opponent",
                right_on="player",
                suffix="_opp",
            )
            .with_columns(
                (pl.col("opp_quality") - pl.col("rating_opp"))
                .round(3)
                .alias("opp_teammate_quality"),
                (pl.col("other_9_players_quality_diff") + pl.col("rating_opp"))
                .round(3)
                .alias("other_8_players_quality_diff"),
            )
            .drop("other_9_players_quality_diff")
        )

        self.teammates = (
            self.teammate_games.with_columns(
                pl.when(pl.col("player") < pl.col("teammate"))
                .then(pl.concat_str(["player", "teammate"], separator=" - "))
                .otherwise(pl.concat_str(["teammate", "player"], separator=" - "))
                .alias("pairing")
            )
            .group_by(["player", "teammate", "pairing"])
            .agg(
                pl.len().alias("games_played"),  # Count of rows in the group
                pl.n_unique("game_date").alias("days_played"),
                pl.sum("winner").alias("wins"),
                (pl.len() - pl.sum("winner")).alias("losses"),
                (pl.sum("winner") / pl.len()).round(3).alias("win_pct"),
                pl.sum("win_prob").round(3).alias("exp_wins"),
                pl.mean("win_prob").round(3).alias("expected_win_pct"),
                (pl.sum("winner") - pl.sum("win_prob")).round(3).alias("wins_over_exp"),
                pl.mean("score_diff").round(3).alias("avg_score_diff"),
                pl.max("game_date").alias("most_recent_game"),
                pl.mean("team_quality").round(3),
                pl.mean("teammate_quality").round(3),
                pl.mean("opp_quality").round(3),
                pl.mean("other_8_players_quality_diff").round(3),
            )
            .sort("wins", "wins_over_exp", "pairing", descending=[True, True, False])
        )

        self.opponents = (
            self.opponent_games.group_by(["player", "opponent"])
            .agg(
                pl.len().alias("games_played"),  # Count of rows in the group
                pl.n_unique("game_date").alias("days_played"),
                pl.sum("winner").alias("wins"),
                (pl.len() - pl.sum("winner")).alias("losses"),
                (pl.sum("winner") / pl.len()).round(3).alias("win_pct"),
                pl.sum("win_prob").round(3).alias("exp_wins"),
                pl.mean("win_prob").round(3).alias("expected_win_pct"),
                (pl.sum("winner") - pl.sum("win_prob")).round(3).alias("wins_over_exp"),
                pl.mean("score_diff").round(3).alias("avg_score_diff"),
                pl.max("game_date").alias("most_recent_game"),
                pl.mean("team_quality").round(3),
                pl.mean("teammate_quality").round(3),
                pl.mean("opp_quality").round(3),
                pl.mean("opp_teammate_quality").round(3),
                pl.mean("other_8_players_quality_diff").round(3),
            )
            .sort(
                "wins",
                "wins_over_exp",
                "player",
                "opponent",
                descending=[True, True, False, False],
            )
        )

        return self.teammate_games, self.opponent_games, self.teammates, self.opponents
