import polars as pl

def filter_player_games(games_data: pl.DataFrame, player_name: str) -> pl.DataFrame:
    """Filters rows where the player exists in team A or team B."""
    a_cols = [f"A{i}" for i in range(1, 6)]
    b_cols = [f"B{i}" for i in range(1, 6)]

    return games_data.filter(
        pl.any_horizontal([pl.col(col) == player_name for col in a_cols + b_cols])
    )

def convert_game_row_to_player_level(row: dict, player_name: str) -> dict:
    """Transforms a row to the new format with additional game data."""
    a_cols = [f"A{i}" for i in range(1, 6)]
    b_cols = [f"B{i}" for i in range(1, 6)]

    if player_name in [row[col] for col in a_cols]:
        team = "A"
        teammates = [row[col] for col in a_cols if row[col] != player_name]
        opponents = [row[col] for col in b_cols]
        team_score, opp_score, team_quality, opp_quality = row["A_SCORE"], row["B_SCORE"], row["A_Quality"], row["B_Quality"]
        spread = -row["Spread"]
        score_diff = -row["Score_Difference"]
        diff_from_spread = -row["Difference_From_Spread"]
    else:
        team = "B"
        teammates = [row[col] for col in b_cols if row[col] != player_name]
        opponents = [row[col] for col in a_cols]
        team_score, opp_score, team_quality, opp_quality = row["B_SCORE"], row["A_SCORE"], row["B_Quality"], row["A_Quality"]
        spread = row["Spread"]  # Flip sign
        score_diff = row["Score_Difference"]  # Flip sign
        diff_from_spread = row["Difference_From_Spread"]  # Flip sign

    return {
        "Date": row["Date"],
        "GameDate": row["GameDate"],
        "GameNum": row["GameNum"],
        "Team": team,
        "Winner": 1 if team == row["Winner"] else 0,
        "Team_Score": team_score,
        "Opp_Score": opp_score,
        "Team_Quality": team_quality,
        "Opp_Quality": opp_quality,
        "Proj_Score_Diff": spread,
        "Final_Score_Diff": score_diff,
        "Spread_Difference": diff_from_spread,
        "T1": teammates[0], "T2": teammates[1], "T3": teammates[2], "T4": teammates[3],
        "O1": opponents[0], "O2": opponents[1], "O3": opponents[2], "O4": opponents[3], "O5": opponents[4]
    }


def create_player_games(games_data: pl.DataFrame, player_name: str, player_rating: float) -> pl.DataFrame:
    """Creates a new dataframe with transformed data for the given player."""
    filtered_games = filter_player_games(games_data, player_name)
    transformed_data = [convert_game_row_to_player_level(row, player_name) for row in filtered_games.iter_rows(named=True)]

    return pl.DataFrame(transformed_data).sort(
        ["GameDate", "GameNum"], descending=[True, True]
    ).with_columns(
        (pl.col('Team_Quality') - pl.lit(player_rating)).round(3).alias('Teammate_Quality')
    ).with_columns(
        (pl.col('Teammate_Quality') - pl.col('Opp_Quality')).round(3).alias('Other_Nine_Player_Quality_Diff')
    )

