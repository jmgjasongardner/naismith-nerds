import polars as pl
from collective_bball.utils import util_code

class PlayerData:
    def __init__(self, games: pl.DataFrame, player_data: pl.DataFrame):
        self.games = games
        self.player_data = player_data
        self.player_stats = None
        self.player_games = None
        self.player_days = None

    def compute_stats(self) -> pl.DataFrame:
        """Extracts player stats from games."""
        team_cols = util_code.player_columns
        id_cols = ["GameDate", "GameNum", "A_SCORE", "B_SCORE", "Winner"]

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
                .then(pl.col("A_SCORE"))
                .otherwise(pl.col("B_SCORE"))
                .alias("team_score"),
                pl.when(pl.col("team") == "A")
                .then(pl.col("B_SCORE"))
                .otherwise(pl.col("A_SCORE"))
                .alias("opponent_score"),
                (pl.col("team") == pl.col("Winner")).cast(pl.Int8).alias("GameWon"),
            )
            .with_columns(
                (pl.col("team_score") - pl.col("opponent_score")).alias("point_diff")
            )
        )

        self.player_stats = (
            players.group_by("player")
            .agg(
                [
                    pl.count("player").alias("games_played"),
                    pl.n_unique("GameDate").alias("days_played"),
                    pl.sum("GameWon").alias("wins"),
                    (pl.count("player") - pl.sum("GameWon")).alias("losses"),
                    (pl.sum("GameWon") / pl.count("player")).round(3).alias("win_pct"),
                    pl.mean("point_diff").round(3).alias("avg_point_diff"),
                ]
            )
            .sort("wins", "losses", "avg_point_diff", descending=[True, False, True])
        )

        return self.player_stats

    def assemble_player_games(self):
        """Combines games & player data into final tables."""
        key_cols = [
            "GameDate", "GameNum", "Day", "Winner", "A_SCORE", "B_SCORE", "A_Quality", "B_Quality",
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
                lambda x: [t for t in x["Teammates"] if t != x["Player"]],
                return_dtype=pl.List(pl.Utf8)
            ).alias("Teammates")
        )
        df_long = df_long.with_columns([
            # Assign team-specific values
            pl.when(pl.col("Team") == "A").then(pl.col("A_SCORE")).otherwise(pl.col("B_SCORE")).alias("Team_Score"),
            pl.when(pl.col("Team") == "A").then(pl.col("B_SCORE")).otherwise(pl.col("A_SCORE")).alias("Opp_Score"),
            pl.when(pl.col("Team") == "A").then(-pl.col("Score_Difference")).otherwise(
                pl.col("Score_Difference")).alias("Score_Difference"),
            pl.when(pl.col("Team") == "A").then(-pl.col("Difference_From_Spread")).otherwise(
                pl.col("Difference_From_Spread")).alias("Difference_From_Spread"),
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
        ]).drop(["PlayerRole", "A_Teammates", "B_Teammates", "A_Opponents", "B_Opponents"]).join(
            self.player_data.select(['player', 'rating']),
            left_on='Player',
            right_on='player',
            how='left'
        ).with_columns(
            (pl.col("Team_Quality") - pl.col("rating")).round(3).alias("Teammate_Quality")
        ).with_columns(
            (pl.col("Teammate_Quality") - pl.col("Opp_Quality")).round(3).alias("Other_9_Players_Quality_Diff")
        )

        # Explode teammates and opponents into separate columns (if needed)
        self.player_games = (df_long.with_columns([
                                                      pl.col("Teammates").list.get(i).alias(f"T{i + 1}") for i in
                                                      range(4)
                                                  ] + [
                                                      pl.col("Opponents").list.get(i).alias(f"O{i + 1}") for i in
                                                      range(5)
                                                  ]).drop(["Teammates", "Opponents", 'A_SCORE', 'B_SCORE',
                                                           'A_Quality', 'B_Quality', 'Spread', 'A_Win_Prob']).select(
            ['GameDate', 'GameNum', 'Day', 'Player', 'rating', 'Team', 'Team_Score', 'Opp_Score', 'Winner', 'Score_Difference',
             'WinProb', 'Moneyline', 'Proj_Score_Diff', 'Difference_From_Spread', 'Team_Quality', 'Teammate_Quality',
             'Opp_Quality', 'Other_9_Players_Quality_Diff',
             'T1', 'T2', 'T3', 'T4', 'O1', 'O2', 'O3', 'O4', 'O5']
        ).sort(["Player", "GameDate", "GameNum"]).with_columns([

            # PlayerGameNum: Count up within each Player, ordered by GameDate -> GameNum
            pl.col("GameNum").cum_count().over("Player").alias("PlayerGameNum"),

            # PlayerWinNum: Running total of wins per player, ordered by GameDate -> GameNum
            pl.col("Winner").cum_sum().over("Player").alias("PlayerWinNum"),

            # PlayerLossNum: Total games played - wins
            (pl.col("GameNum").cum_count().over("Player") - pl.col("Winner").cum_sum().over("Player"))
            .alias("PlayerLossNum"),
            # PlayerDayGameNum: Count up within each (Player, GameDate), ordered by GameNum
            pl.col("GameNum").cum_count().over(["Player", "GameDate"]).alias("PlayerDayGameNum"),

            # Identify FirstGame (1 if first row for player, 0 otherwise)
            (pl.col("GameNum") == pl.col("GameNum").min().over(["Player", "GameDate"])).cast(pl.Int8).alias(
                "FirstGameOfDay"),
            (pl.col("GameNum") == pl.col("GameNum").max().over(["Player", "GameDate"])).cast(pl.Int8).alias(
                "LastGameOfDay"),
            (pl.col("GameNum") == pl.col("GameNum").min().over(["GameDate"])).cast(pl.Int8).alias("PlayedFirstGame"),
            (pl.col("GameNum") == pl.col("GameNum").max().over(["GameDate"])).cast(pl.Int8).alias("PlayedLastGame")
        ]).with_columns([
            # Calculate GamesWaited (days since last appearance)
            (pl.col("GameNum") - pl.col("GameNum").shift(1).over(["Player", "GameDate"]) - 1)
            .fill_null(0)
            .alias("GamesWaited"),

            # Identify resets: Either a new GameDate or a missing GameNum
            ((pl.col("GameNum") - pl.col("GameNum").shift(1).over(["Player", "GameDate"]) > 1) |
             (pl.col("GameDate") != pl.col("GameDate").shift(1).over(["Player", "GameDate"])))
            .fill_null(True)  # First row should be considered a reset
            .cast(pl.Int8)
            .alias("GameReset")
        ]).with_columns([
            # Initialize ConsecutiveGames with 0 and mark the first game or reset points
            pl.when(pl.col("GameReset") == 1).then(pl.lit(0)).otherwise(pl.lit(1)).alias("ConsecutiveGamesInitial")
        ]).with_columns([
            # Calculate ConsecutiveGames based on resets
            pl.when(pl.col("GameReset") == 1)
            .then(pl.lit(0))
            .otherwise(pl.col("ConsecutiveGamesInitial").cum_sum().over(["Player", "GameDate"]))
            .alias("ConsecutiveGames")
        ]).drop(["GameReset", "ConsecutiveGamesInitial"])
        )
        return self.player_games

    def assemble_player_days(self):
        self.player_days = self.player_games.group_by(["Player", "GameDate", "Day", "rating"]).agg(
            pl.count("Player").alias("GP"),
            pl.sum("Winner").alias("Ws"),
            (pl.count("Player") - pl.sum("Winner")).alias("Ls"),
            (pl.sum("Winner") / pl.count("Player")).round(3).alias("Win%"),
            pl.mean("WinProb").round(3).alias("Exp_Win%"),
            pl.mean("Proj_Score_Diff").round(3),
            pl.mean("Teammate_Quality").round(3).alias("Teammates_Avg"),
            pl.mean("Opp_Quality").round(3).alias("Opps_Avg"),
            pl.mean("Other_9_Players_Quality_Diff").round(3).alias("Other_9_Player_Avg"),
            pl.sum("PlayedFirstGame"),
            pl.sum("PlayedLastGame"),
            pl.min("GameNum").alias("FirstGameOfDay"),
            pl.max("GameNum").alias("LastGameOfDay"),
            pl.max("ConsecutiveGames").alias("LongestRunOnCourt"),
            pl.max("GamesWaited").alias("LongestRunOnBench")
        ).sort("GameDate", "FirstGameOfDay", "Player", descending=[True, False, False])
        return self.player_days

    def combine_player_stats_with_games_groupings(self):
        self.player_data = self.player_data.join(
            self.player_games.group_by(["Player"]).agg(
                pl.sum('WinProb').round(3).alias('ExpectedWins'),
                (pl.sum('WinProb') / pl.count('Player')).round(3).alias('ExpectedWinPct'),
                pl.mean('Proj_Score_Diff').round(3).alias('Proj_Score_Diff'),
                (pl.count('Player') / len(self.games)).round(3).alias('PctTotalGamesPlayed'),
                (pl.n_unique('GameDate') / len(self.games['GameDate'].unique())).round(3).alias('PctTotalDaysPlayed'),
                pl.mean('Teammate_Quality').round(3),
                pl.mean('Team_Quality').round(3),
                pl.mean('Opp_Quality').round(3),
                pl.col('Teammate_Quality').gt(0).mean().round(3).alias('PercentPositiveTeammates'),
                pl.col('Opp_Quality').gt(0).mean().round(3).alias('PercentPositiveOpponents'),
                pl.col('Proj_Score_Diff').gt(0).mean().round(3).alias('PctGamesFavorite'),
                (pl.col('Opp_Quality') < pl.col('Teammate_Quality')).mean().round(3).alias('PctGamesBetterTeammates'),
                pl.mean('Other_9_Players_Quality_Diff').round(3),

        ),
            left_on="player",
            right_on="Player",
            how="inner"
        ).join(
            self.player_days.group_by(["Player"]).agg(
                pl.mean('GP').round(3).alias('GamesPlayedPerDay'),
                (pl.sum('PlayedFirstGame') / pl.count('Player')).round(3).alias('FirstGameOfDayRate'),
                (pl.sum('PlayedLastGame') / pl.count('Player')).round(3).alias('LastGameOfDayRate'),
                ((pl.when(pl.col('Day') == 'Mon').then(1).otherwise(0)).sum() /
                 self.games.filter(pl.col("Day") == "Mon")["GameDate"].n_unique()).round(3).alias("MonRate"),
                ((pl.when(pl.col('Day') == 'Wed').then(1).otherwise(0)).sum() /
                 self.games.filter(pl.col("Day") == "Wed")["GameDate"].n_unique()).round(3).alias("WedRate"),
                ((pl.when(pl.col('Day') == 'Sat').then(1).otherwise(0)).sum() /
                 self.games.filter(pl.col("Day") == "Sat")["GameDate"].n_unique()).round(3).alias("SatRate")


        ),
            left_on="player",
            right_on="Player",
            how="inner"
        )

        return self.player_data
