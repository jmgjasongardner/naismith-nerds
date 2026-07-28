"""
Describes how each column should be labelled, typed and formatted.

The browser gets this spec alongside the raw values and does the rendering, so
formatting rules live in one place instead of being repeated in every template.

Types the front end understands:
    player  linked name with avatar
    date    linked game date
    text    plain string
    int     whole number
    num     decimal, rounded to `dp`
    pct     0-1 fraction shown as a percentage
    signed  decimal that is colored by sign
"""

from typing import Dict, List

import polars as pl

# Human labels. Extends the map the classic site used so both stay consistent.
LABELS: Dict[str, str] = {
    "player": "Player",
    "teammate": "Teammate",
    "opponent": "Opp",
    "pairing": "Pairing",
    "game_date": "Date",
    "most_recent_game": "Last Game",
    "day": "Day",
    "rating": "Rating",
    "resident": "Resident",
    "games_played": "G",
    "days_played": "Days",
    "wins": "W",
    "losses": "L",
    "win_pct": "Win%",
    "expected_wins": "xW",
    "exp_wins": "xW",
    "expected_win_pct": "xWin%",
    "exp_win_pct": "xWin%",
    "wins_over_exp": "W-xW",
    "avg_score_diff": "Avg Diff",
    "proj_score_diff": "Proj Diff",
    "teammates_avg": "Tm Avg Rtg",
    "opps_avg": "Opp Avg Rtg",
    "other_9_player_avg": "Other 9 Avg",
    "result_vs_expectation_avg": "Gospel",
    "result_vs_expectation": "Gospel",
    "gospel_as_teammates": "Gospel w/ Tm",
    "gospel_vs_opponent": "Gospel vs Opp",
    "played_first_game": "Played 1st",
    "played_last_game": "Played Last",
    "first_game_of_day": "1st Game",
    "last_game_of_day": "Last Game",
    "first_game_of_day_rate": "1st Game Rate",
    "last_game_of_day_rate": "Last Game Rate",
    "longest_run_on_court": "Longest Run On",
    "longest_run_on_bench": "Longest Run Off",
    "avg_longest_run_on_court": "Avg Run On",
    "avg_longest_run_on_bench": "Avg Run Off",
    "a_score": "A",
    "b_score": "B",
    "winner": "Winner",
    "game_num": "Game #",
    "a_quality": "A Quality",
    "b_quality": "B Quality",
    "team_quality": "Team Quality",
    "teammate_quality": "Teammate Qual",
    "opp_quality": "Opp Quality",
    "opp_teammate_quality": "Opp Tm Quality",
    "other_8_players_quality_diff": "Other 8 Diff",
    "other_9_players_quality_diff": "Other 9 Diff",
    "spread": "Spread",
    "score_diff": "Score Diff",
    "diff_from_spread": "vs Spread",
    "absolute_spread": "|Spread|",
    "absolute_score_diff": "|Score Diff|",
    "absolute_spread_diff": "|vs Spread|",
    "a_win_prob": "A Win Prob",
    "win_prob": "Win Prob",
    "moneyline": "Moneyline",
    "num_players": "Players",
    "mvp": "MVP",
    "mvp_gospel": "MVP Gospel",
    "lvp": "LVP",
    "lvp_gospel": "LVP Gospel",
    "mvps": "MVPs",
    "lvps": "LVPs",
    "mvp_pct": "MVP%",
    "lvp_pct": "LVP%",
    "residents": "Residents",
    "resident_rate": "Resident%",
    "num_games": "Games",
    "mean_rating_players": "Avg Rtg (Players)",
    "mean_rating_player_games": "Avg Rtg (Games)",
    "unique_winners_rate": "Unique Winners",
    "avg_parity_of_teammates": "Parity: Teammates",
    "avg_parity_of_teams": "Parity: Teams",
    "avg_parity_of_score_diff": "Parity: Score",
    "avg_parity_of_spread": "Parity: Spread",
    "avg_parity_of_win_probs": "Parity: Win Prob",
    "team": "Team",
    "team_score": "Team Score",
    "opp_score": "Opp Score",
    "pct_total_games_played": "% All Games",
    "pct_total_days_played": "% All Days",
    "pct_positive_teammates": "% Pos Teammates",
    "pct_positive_opponents": "% Pos Opps",
    "pct_games_favorite": "% as Favorite",
    "pct_games_better_teammates": "% Better Tm",
    "games_played_per_day": "G/Day",
    "player_game_num": "Career Game",
    "player_win_num": "Career W",
    "player_loss_num": "Career L",
    "player_day_game_num": "Game of Day",
    "games_waited": "Games Waited",
    "consecutive_games": "Games On",
    "mon_rate": "Mon%",
    "wed_rate": "Wed%",
    "sat_rate": "Sat%",
    "first_poss": "1st Poss",
    "clock": "Clock",
    "active_player": "Active",
    "full_name": "Name",
    "height": "Height",
    "position": "Position",
    "birthday": "Birthday",
    "team_total_games_played_A": "A Games Today",
    "team_total_games_played_B": "B Games Today",
}

# Explanations surfaced as column tooltips.
TIPS: Dict[str, str] = {
    "rating": (
        "RAPM rating: points per game this player is worth versus a "
        "replacement-level player. 0 is average; higher is better."
    ),
    "result_vs_expectation": (
        "The Gospel. Actual score differential minus what the model projected, "
        "averaged over games. Positive means outperforming expectation."
    ),
    "result_vs_expectation_avg": (
        "The Gospel. Actual minus projected score differential, averaged."
    ),
    "gospel_as_teammates": "Result versus expectation when these two play together.",
    "gospel_vs_opponent": "Result versus expectation when these two play against each other.",
    "spread": "Pregame spread relative to team A. Positive means A is the underdog.",
    "diff_from_spread": "Score differential minus the spread. How much the spread was beaten by.",
    "a_quality": "Sum of team A player ratings. 0 is an average five.",
    "b_quality": "Sum of team B player ratings. 0 is an average five.",
    "team_quality": "Sum of team ratings, including the player.",
    "teammate_quality": "Sum of teammate ratings, excluding the player.",
    "opp_quality": "Sum of opponent ratings.",
    "other_9_players_quality_diff": (
        "Average difference between teammate and opponent ratings. Positive "
        "means this player usually had the stronger nine around them."
    ),
    "avg_score_diff": "Average score differential across the player's games.",
    "proj_score_diff": "Sum of team ratings minus opponent ratings.",
    "pct_positive_teammates": "Share of games where teammates are net positive.",
    "pct_positive_opponents": "Share of games where opponents are net positive.",
    "pct_games_favorite": "Share of games where the team is favored.",
    "pct_games_better_teammates": (
        "Share of games with better teammates than opponents."
    ),
    "first_game_of_day_rate": "Share of runs where the player appears in the first game.",
    "last_game_of_day_rate": "Share of runs where the player appears in the last game.",
    "wins": "Games won.",
    "losses": "Games lost.",
    "win_pct": "Share of games won.",
    "expected_wins": "Wins the model expected given the lineups faced.",
    "expected_win_pct": "Win rate the model expected given the lineups faced.",
    "games_played": "Total games played.",
    "days_played": "Total runs attended.",
    "games_played_per_day": "Average games played per run attended.",
    "pct_total_games_played": "Share of every game ever played that this player was in.",
    "pct_total_days_played": "Share of every run that this player attended.",
    "mon_rate": "Share of Monday runs attended.",
    "wed_rate": "Share of Wednesday runs attended.",
    "sat_rate": "Share of Saturday runs attended.",
    "most_recent_game": "Date of this player's most recent run.",
    "win_prob": "Modelled pregame win probability for this player's team.",
    "moneyline": "Pregame win probability expressed as American odds.",
    "exp_wins": "Wins the model expected given the lineups faced.",
    "wins_over_exp": "Actual wins minus expected wins.",
    "unique_winners_rate": "Share of players on the day who won at least one game.",
    "avg_parity_of_teams": "Spread of team strength across the day. Lower means more balanced.",
    "clock": "Whether the game was played to a running clock rather than a fixed score.",
    "mvps": "Days this player was the run's MVP.",
    "lvps": "Days this player was the run's LVP.",
    "mvp_pct": "Share of the days played where this player was MVP.",
    "lvp_pct": "Share of the days played where this player was LVP.",
    "mvp": (
        "Best result versus expectation that day, among players with at least "
        "three games. Ties break alphabetically."
    ),
    "lvp": (
        "Worst result versus expectation that day, among players with at least "
        "three games. Ties break alphabetically."
    ),
    "first_poss": "Which team started with the ball, inferred from who held the court.",
    "active_player": "Played within the last 90 days.",
    "resident": "Plays regularly at this run.",
}

# Columns that read as identities rather than measurements.
PLAYER_COLUMNS = {
    "player", "teammate", "opponent", "mvp", "lvp",
    *(f"A{i}" for i in range(1, 6)),
    *(f"B{i}" for i in range(1, 6)),
    *(f"T{i}" for i in range(1, 5)),
    *(f"O{i}" for i in range(1, 6)),
}

DATE_COLUMNS = {"game_date", "most_recent_game"}

# Measurements centered on zero, where the sign carries the meaning.
SIGNED_COLUMNS = {
    "rating", "avg_score_diff", "proj_score_diff", "score_diff", "spread",
    "diff_from_spread", "result_vs_expectation", "result_vs_expectation_avg",
    "gospel_as_teammates", "gospel_vs_opponent", "wins_over_exp",
    "mvp_gospel", "lvp_gospel",
    "other_8_players_quality_diff", "other_9_players_quality_diff",
    "a_quality", "b_quality", "team_quality", "teammate_quality",
    "opp_quality", "opp_teammate_quality", "teammates_avg", "opps_avg",
    "other_9_player_avg", "mean_rating_players", "mean_rating_player_games",
}

PCT_COLUMNS = {
    "win_pct", "expected_win_pct", "exp_win_pct", "resident_rate",
    "unique_winners_rate", "win_prob", "a_win_prob", "pct_total_games_played",
    "pct_total_days_played", "pct_positive_teammates", "pct_positive_opponents",
    "pct_games_favorite", "pct_games_better_teammates",
    "first_game_of_day_rate", "last_game_of_day_rate",
    "mvp_pct", "lvp_pct",
    "mon_rate", "wed_rate", "sat_rate",
}

# Decimal places by column, defaulting to 2.
DECIMALS: Dict[str, int] = {
    "rating": 2,
    "win_prob": 3,
    "a_win_prob": 3,
}

_INT_TYPES = (
    pl.Int8, pl.Int16, pl.Int32, pl.Int64,
    pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
)


def label_for(column: str) -> str:
    return LABELS.get(column, column.replace("_", " ").title())


def type_for(column: str, dtype) -> str:
    if column == "pairing":
        # "A - B": rendered as two separate links, not one string.
        return "pairing"
    if column in PLAYER_COLUMNS:
        return "player"
    if column in DATE_COLUMNS:
        return "date"
    if column in PCT_COLUMNS:
        return "pct"
    if column in SIGNED_COLUMNS:
        return "signed"
    if dtype == pl.Boolean:
        return "bool"
    if dtype in _INT_TYPES:
        return "int"
    if dtype in (pl.Float32, pl.Float64):
        return "num"
    return "text"


def spec_for(df: pl.DataFrame) -> List[dict]:
    """Build the column spec the browser renders from."""
    columns = []
    for name, dtype in zip(df.columns, df.dtypes):
        kind = type_for(name, dtype)
        entry = {"key": name, "label": label_for(name), "type": kind}
        if kind == "pct":
            # Displayed after multiplying by 100, so one decimal is plenty.
            # DECIMALS governs stored precision, not what is shown.
            entry["dp"] = 1
        elif kind in ("num", "signed"):
            entry["dp"] = DECIMALS.get(name, 2)
        tip = TIPS.get(name)
        if tip:
            entry["tip"] = tip
        columns.append(entry)
    return columns


def round_floats(df: pl.DataFrame) -> pl.DataFrame:
    """Round floats before serialising.

    Full float64 repr costs ~17 characters per value. Across ten thousand rows
    that is most of the payload, and none of it is displayed.
    """
    expressions = []
    for name, dtype in zip(df.columns, df.dtypes):
        if dtype not in (pl.Float32, pl.Float64):
            continue
        if name in PCT_COLUMNS:
            places = 4
        else:
            places = DECIMALS.get(name, 3)
        expressions.append(pl.col(name).round(places))
    return df.with_columns(expressions) if expressions else df
