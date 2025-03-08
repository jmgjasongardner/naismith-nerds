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
        team_score, opp_score, team_quality, opp_quality = (
            row["A_SCORE"],
            row["B_SCORE"],
            row["A_Quality"],
            row["B_Quality"],
        )
        spread = -row["Spread"]
        moneyline = row["Moneyline"]
        win_pct = row["A_Win_Prob"]
        score_diff = -row["Score_Difference"]
        diff_from_spread = -row["Difference_From_Spread"]
    else:
        team = "B"
        teammates = [row[col] for col in b_cols if row[col] != player_name]
        opponents = [row[col] for col in a_cols]
        team_score, opp_score, team_quality, opp_quality = (
            row["B_SCORE"],
            row["A_SCORE"],
            row["B_Quality"],
            row["A_Quality"],
        )
        spread = row["Spread"]  # Flip sign
        moneyline = -row["Moneyline"]  # Flip sign
        win_pct = 1 - row["A_Win_Prob"]
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
        "Moneyline": moneyline,
        "Final_Score_Diff": score_diff,
        "Spread_Difference": diff_from_spread,
        "T1": teammates[0],
        "T2": teammates[1],
        "T3": teammates[2],
        "T4": teammates[3],
        "O1": opponents[0],
        "O2": opponents[1],
        "O3": opponents[2],
        "O4": opponents[3],
        "O5": opponents[4],
        "WinProb": round(win_pct, 3),
    }


def create_player_games(
    games_data: pl.DataFrame, player_name: str, player_ratings: pl.DataFrame
) -> pl.DataFrame:
    """Creates a new dataframe with transformed data for the given player."""
    player_rating = player_ratings.filter(pl.col("Player") == player_name)[
        "Rating"
    ].item()
    filtered_games = filter_player_games(games_data, player_name)
    transformed_data = [
        convert_game_row_to_player_level(row, player_name)
        for row in filtered_games.iter_rows(named=True)
    ]

    return (
        pl.DataFrame(transformed_data)
        .sort(["GameDate", "GameNum"], descending=[True, True])
        .with_columns(
            (pl.col("Team_Quality") - pl.lit(player_rating))
            .round(3)
            .alias("Teammate_Quality")
        )
        .with_columns(
            (pl.col("Teammate_Quality") - pl.col("Opp_Quality"))
            .round(3)
            .alias("Other_Nine_Player_Quality_Diff")
        )
    )


def create_player_games_advanced(player_games: pl.DataFrame, games_data: pl.DataFrame):
    num_games = len(player_games)
    player_games = player_games.with_columns(
        pl.when(pl.col("Proj_Score_Diff") > 0).then(1).otherwise(0).alias("Favorite")
    )

    win_pct = [
        {
            "Expected Wins": round(sum(player_games["WinProb"]), 3),
            "Expected Win Pct": round(
                sum(player_games["WinProb"]) / len(player_games), 3
            ),
            "Expected Pt Differential": round(
                sum(player_games["Proj_Score_Diff"]) / len(player_games), 3
            ),
        }
    ]

    player_games_advanced = pl.DataFrame(
        {
            "Pct Total Games Played": [round(len(player_games) / len(games_data), 3)],
            "Pct Total Days Played": [
                round(
                    len(player_games["Date"].unique())
                    / len(games_data["Date"].unique()),
                    3,
                )
            ],
            "Pct First Games Played": [
                round(
                    sum(player_games["GameNum"] == 1)
                    / len(player_games["Date"].unique()),
                    3,
                )
            ],
            "Pct Games w/ Positive Teammates": [
                round((player_games["Teammate_Quality"] > 0).sum() / num_games, 3)
            ],
            "Pct Games w/ Positive Opponents": [
                round((player_games["Opp_Quality"] > 0).sum() / num_games, 3)
            ],
            "Pct Games w/ Better Teammates": [
                round(
                    (player_games["Other_Nine_Player_Quality_Diff"] > 0).sum()
                    / num_games,
                    3,
                )
            ],
            "Pct Games as Favorite": [
                round((player_games["Proj_Score_Diff"] > 0).sum() / num_games, 3)
            ],
            "Win Pct as Favorite": [
                (
                    "N/A"
                    if player_games["Favorite"].sum() == 0
                    else round(
                        player_games.filter(pl.col("Favorite") == 1)["Winner"].sum()
                        / player_games["Favorite"].sum(),
                        3,
                    )
                )
            ],
            "Win Pct as Underdog": [
                (
                    "N/A"
                    if (player_games["Favorite"] == 0).sum() == 0
                    else round(
                        player_games.filter(pl.col("Favorite") == 0)["Winner"].sum()
                        / (player_games["Favorite"] == 0).sum(),
                        3,
                    )
                )
            ],
        }
    )

    biggest_upset_win = (
        player_games.filter((pl.col("Winner") == 1) & (pl.col("Favorite") == 0))
        .sort("Proj_Score_Diff")
        .head(1)
        .with_columns(pl.lit("Biggest Upset Win").alias("Game Type"))
        .select(["Game Type", *player_games.columns])
    )

    biggest_upset_loss = (
        player_games.filter((pl.col("Winner") == 0) & (pl.col("Favorite") == 1))
        .sort("Proj_Score_Diff", descending=True)
        .head(1)
        .with_columns(pl.lit("Biggest Upset Loss").alias("Game Type"))
        .select(["Game Type", *player_games.columns])
    )

    most_impressive = (
        player_games.sort("Spread_Difference", descending=True)
        .head(1)
        .with_columns(pl.lit("Most Impressive").alias("Game Type"))
        .select(["Game Type", *player_games.columns])
    )

    most_embarrassing = (
        player_games.sort("Spread_Difference")
        .head(1)
        .with_columns(pl.lit("Most Embarrassing").alias("Game Type"))
        .select(["Game Type", *player_games.columns])
    )

    # Concatenate while ensuring only non-empty results are included
    games_of_note = pl.concat(
        [biggest_upset_win, biggest_upset_loss, most_impressive, most_embarrassing],
        how="vertical",
    ).drop_nulls(subset=["Game Type"])

    return win_pct, player_games_advanced, games_of_note


def load_player_bio_data(bios: pl.DataFrame, player_name: str):

    # Look up bio information
    bio_row = bios.filter(pl.col("player") == player_name)

    # Default to player_name if full_name is missing
    full_name = bio_row["full_name"].item() if not bio_row.is_empty() else player_name
    position = bio_row["position"].item() if not bio_row.is_empty() else None

    # Convert height from inches to "ft, in" format if available
    if not bio_row.is_empty() and bio_row["height"].is_not_null().all():
        height_in = int(bio_row["height"].item())
        height_ft = height_in // 12
        height_remain = height_in % 12
        height_str = f"Height: {height_ft}'{height_remain}\""
    else:
        height_str = None  # No height available

    return full_name, height_str, position
