import polars as pl
import logging


def format_stats_for_site(df: pl.DataFrame):
    #logging.debug(f"In format_stats_for_site")
    """Rename columns and round numeric values before passing to Jinja."""
    column_map = {
        "player": "Player",
        "game_date": "Game Date",
        "day": "Day",
        "rating": "Rating",
        "games_played": "Games Played",
        "days_played": "Days Played",
        "wins": "Wins",
        "losses": "Losses",
        "win_pct": "Win Pct",
        "win_%": "Win Pct",
        "expected_wins": "Exp Wins",
        "expected_win_pct": "Exp Win Pct",
        "exp_win_pct": "Exp Win Pct",
        "avg_score_diff": "Avg Score Diff",
        "proj_score_diff": "Proj Score Diff",
        "teammates_avg": "Teammates Avg Rating",
        "opps_avg": "Opps Avg Rating",
        "other_9_player_avg": "Other 9 Players' Avg Rating",
        "played_first_game": "Played First Game",
        "played_last_game": "Played Last Game",
        "first_game_of_day": "First Game Day",
        "last_game_of_day": "Last Game Day",
        "longest_run_on_court": "Longest Run on Court",
        "longest_run_on_bench": "Longest Run on Bench",
        "a_score": "A Score",
        "b_score": "B Score",
        "winner": "Winner",
        "game_num": "Game Number",
        "a_quality": "Team A Quality",
        "b_quality": "Team B Quality",
        "spread": "Spread",
        "score_diff": "Score Diff",
        "diff_from_spread": "Diff from Spread",
        "absolute_spread": "Abs Spread",
        "absolute_score_diff": "Abs Score Diff",
        "absolute_spread_diff": "Abs Spread Diff",
        "a_win_prob": "Team A Win Prob",
        "moneyline": "Moneyline",
        "num_players": "Num Players",
        "num_games": "Num Games",
        "mean_rating_players": "Mean Rating Players",
        "mean_rating_player_games": "Mean Rating Player Games",
        "avg_longest_run_on_court": "Avg Longest Run on Court",
        "avg_longest_run_on_bench": "Avg Longest Run on Bench",
        "unique_winners_rate": "Unique Winners Rate",
        "avg_parity_of_teammates": "Avg Parity of Teammates",
        "avg_parity_of_teams": "Avg Parity of Teams",
        "avg_parity_of_score_diff": "Avg Parity of Score Diff",
        "avg_parity_of_spread": "Avg Parity of Spread",
        "avg_parity_of_win_probs": "Avg Parity of Win Probs",
        "team": "Team",
        "team_score": "Team Score",
        "opp_score": "Opp Score",
        "win_prob": "Win Prob",
        "opponent": "Opp",
        "rating_opp": "Opp Rating",
        "opp_teammate_quality": "Opp Teammate Quality",
        "other_8_players_quality_diff": "Other 8 Players' Quality Diff",
        "teammate": "Teammate",
        "rating_teammate": "Teammate Rating",
        "pairing": "Pairing",
        "exp_wins": "Exp Wins",
        "wins_over_exp": "Wins Over Exp",
        "most_recent_game": "Most Recent Game",
        "team_quality": "Team Quality",
        "teammate_quality": "Teammate Quality",
        "opp_quality": "Opp Quality",
        "pct_total_games_played": "Pct Total Games Played",
        "pct_total_days_played": "Pct Total Days Played",
        "pct_positive_teammates": "Pct Positive Teammates",
        "pct_positive_opponents": "Pct Positive Opps",
        "pct_games_favorite": "Pct Games as Favorite",
        "pct_games_better_teammates": "Pct Games w/ Better Teammates",
        "other_9_players_quality_diff": "Other 9 Players' Quality Diff",
        "games_played_per_day": "Games Played Per Day",
        "first_game_of_day_rate": "First Game Day Rate",
        "last_game_of_day_rate": "Last Game Day Rate",
        "player_game_num": "Player Career Game Num",
        "player_win_num": "Player Career Wins",
        "player_loss_num": "Player Career Losses",
        "player_day_game_num": "Player Day Game Num",
        "games_waited": "Num Games Waited",
        "consecutive_games": "Num Games On Court",
        "mon_rate": "Mon Rate",
        "wed_rate": "Wed Rate",
        "sat_rate": "Sat Rate",
    }
    # logging.debug(f"ratings sample df in web_data_loader as polars: {df.head(5)}")
    #df = df.head(5)
    columns_in_df = df.columns
    filtered_column_map = {k: v for k, v in column_map.items() if k in columns_in_df}
    # logging.debug(f"original column map in web_data_loader: {column_map}")
    # logging.debug(f"filtered column map in web_data_loader: {filtered_column_map}")

    df = df.rename(filtered_column_map)
    # logging.debug(f"Original df in web_data_loader polars: {df}")

    # Round numeric columns (here, we assume 'Rating' column needs rounding to 5 decimals)
    df = df.with_columns([
        pl.col(col).round(5).alias(col) if col == "rating" else pl.col(col).round(3).alias(col)
        for col in df.columns if df[col].dtype in [pl.Float32, pl.Float64]  # Check for numeric columns
    ])

    logging.debug(f"df with rounding in web_data_loader polars: {df}")

    # Convert to list of dictionaries
    output_dict = df.to_dicts()  # This gives you a list of dictionaries
    logging.debug(f"ratings sample dict in web_data_loader: {output_dict}")

    return output_dict


# def get_model_outputs():
#     """Fetch ratings as a pandas dataframe."""
#     ratings_df, best_lambda, tiers, bios = run_rapm_model()
#     ratings_df = ratings_df.with_columns(pl.col("rating").round(5)).rename(
#         {"player": "Player", "rating": "Rating"}
#     )
#     return ratings_df, best_lambda, tiers, bios


# def combine_tier_ratings(stats, ratings, tiers) -> pl.DataFrame:
#     combined_ratings = (
#         stats.join(ratings, left_on="player", right_on="Player", how="left")
#         .join(tiers, left_on="player", right_on="player", how="left")
#         .join(ratings, left_on="tier", right_on="Player", how="left")
#         .with_columns(pl.col("Rating").fill_null(pl.col("Rating_right")))
#         .rename({"player": "Player"})
#         .select(["Player", "Rating"])
#         .sort("Rating", "Player", descending=[True, False])
#     )
#
#     return combined_ratings


# def calculate_game_spreads(games, ratings) -> pl.DataFrame:
#
#     games_long = (
#         games.unpivot(
#             index=["GameDate", "GameNum"],
#             on=["A1", "A2", "A3", "A4", "A5", "B1", "B2", "B3", "B4", "B5"],
#             variable_name="team_role",
#             value_name="Player",
#         )
#         .join(ratings, on="Player", how="left")
#         .with_columns(
#             (pl.col("team_role").str.starts_with("A") * pl.col("Rating")).alias(
#                 "A_Rating"
#             ),
#             (pl.col("team_role").str.starts_with("B") * pl.col("Rating")).alias(
#                 "B_Rating"
#             ),
#         )
#         .group_by(["GameDate", "GameNum"])
#         .agg(
#             pl.sum("A_Rating").round(3).alias("A_Quality"),
#             pl.sum("B_Rating").round(3).alias("B_Quality"),
#         )
#         .with_columns(
#             (pl.col("B_Quality") - pl.col("A_Quality")).round(3).alias("Spread")
#         )
#     )
#
#     games_with_spreads = (
#         games.join(games_long, on=["GameDate", "GameNum"], how="inner")
#         .with_columns((pl.col("B_SCORE") - pl.col("A_SCORE")).alias("Score_Difference"))
#         .with_columns(
#             (pl.col("Score_Difference") - pl.col("Spread"))
#             .round(3)
#             .alias("Difference_From_Spread")
#         )
#         .with_columns(
#             (pl.col("Spread").abs()).alias("Absolute_Spread"),
#             (pl.col("Score_Difference").abs()).alias("Absolute_Score_Difference"),
#             (pl.col("Difference_From_Spread").abs()).alias(
#                 "Absolute_Spread_Difference"
#             ),
#         )
#     )
#
#     return games_with_spreads
