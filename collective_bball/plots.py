import polars as pl
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


class Plots:
    def __init__(self, conn):
        self.conn = conn  # Store the connection inside the class
        self.plot_ratings = None  # Placeholder for the plot

    def plot_ratings_time(self):
        # Fetch data from DuckDB and convert it to Polars
        df_pandas = self.conn.execute(
            "SELECT * FROM ratings WHERE player NOT ILIKE '%tier%'"
        ).fetch_df()

        df_pandas["days_since_graduation"] = df_pandas.groupby("player")[
            "player"
        ].transform("count")

        df_pandas = df_pandas.sort_values(
            by=["days_since_graduation", "player", "date"],
            ascending=[False, False, True],
        )

        # Ensure 'date' is a datetime object for sorting
        df_pandas["date"] = pd.to_datetime(df_pandas["date"])
        fig = px.line(
            df_pandas,
            x="date",
            y="rating",
            color="player",
            labels={"x": "Date", "y": "Rating"},
            title="Player Ratings Over Time <br><sup>Double click on a player to filter to them and click to add others. Draw area to zoom.</sup>",
        )
        # fig.show()

        self.plot_ratings = fig.to_html(full_html=False)

        return self.plot_ratings

    def plot_rapm_vs_apm(self, player_data: pl.DataFrame):
        # Fetch data from DuckDB and convert it to Polars
        fig = px.scatter(
            player_data.filter(pl.col("tiered_rating") == 0),
            x="result_vs_expectation",
            y="rating",
            size="games_played",
            color="win_pct",
            hover_data=["player"],
            title="RAPM Player Rating vs APM Player Rating",
            labels={
                "result_vs_expectation": "APM = Avg Score Diff Minus (Average Rating of Teammates - Opposition)",
                "rating": "Regularized Version of APM (Rating)",
                "win_pct": "Win Pct",
            },
        )

        fig.add_trace(
            go.Scatter(
                x=[-5, 5],
                y=[-5, 5],
                mode="lines",
                name="y = x",
                line=dict(dash="dash", color="black"),
            )
        )

        fig.update_layout(
            xaxis=dict(range=[-5, 5]),
            yaxis=dict(range=[-5, 5]),
            title=dict(
                text="RAPM Player Rating vs APM Player Rating<br>"
                "<sub>Bubble size reflects number of games played</sub>"
            ),
        )
        self.plot_rapm_apm = fig.to_html(full_html=False)

        return self.plot_rapm_apm

    def plot_player_ratings_time(self, player_name: str):
        # Fetch data from DuckDB and convert it to Polars
        df_pandas = self.conn.execute(
            f"SELECT * FROM ratings WHERE player = '{player_name}'"
        ).fetch_df()

        df_pandas = df_pandas.sort_values(by=["date"], ascending=[True])

        # Ensure 'date' is a datetime object for sorting
        df_pandas["date"] = pd.to_datetime(df_pandas["date"])
        fig = px.line(
            df_pandas,
            x="date",
            y="rating",
            labels={"x": "Date", "y": "Rating"},
            title=f"{player_name}'s Ratings Over Time <br><sup>Draw area to zoom.</sup>",
        )

        return fig

    def plot_player_rolling_avg(
        self, player_name: str, player_games: pl.DataFrame, rolling_games=20
    ):
        df = (
            player_games.filter(pl.col("player") == player_name)
            .select(
                [
                    "player_game_num",
                    "game_date",
                    "result_vs_expectation",
                    "other_9_players_quality_diff",
                    "teammate_quality",
                    "opp_quality",
                    "winner",
                ]
            )
            .sort("player_game_num")
            .with_columns(
                [
                    # rolling averages for all metrics
                    pl.col("result_vs_expectation")
                    .rolling_mean(window_size=rolling_games)
                    .alias("rolling_result_vs_expectation"),
                    pl.col("other_9_players_quality_diff")
                    .rolling_mean(window_size=rolling_games)
                    .alias("rolling_other_9_players_quality_diff"),
                    pl.col("teammate_quality")
                    .rolling_mean(window_size=rolling_games)
                    .alias("rolling_teammate_quality"),
                    pl.col("opp_quality")
                    .rolling_mean(window_size=rolling_games)
                    .alias("rolling_opp_quality"),
                    pl.col("winner")
                    .rolling_mean(window_size=rolling_games)
                    .alias("rolling_winner"),
                    # start date of rolling window
                    pl.col("game_date")
                    .shift(rolling_games - 1)
                    .alias("rolling_start_date"),
                ]
            )
            .with_columns(
                [
                    # rolling date range for tooltip
                    (pl.col("rolling_start_date") + " to " + pl.col("game_date")).alias(
                        "rolling_date_range"
                    )
                ]
            )
        )

        # Convert to pandas
        df_pandas = df.to_pandas()

        # Melt DataFrame so each rolling metric is a variable for Plotly Express
        df_melted = df_pandas.melt(
            id_vars=["player_game_num", "rolling_date_range"],
            value_vars=[
                "rolling_result_vs_expectation",
                "rolling_other_9_players_quality_diff",
                "rolling_teammate_quality",
                "rolling_opp_quality",
                "rolling_winner",
            ],
            var_name="Metric",
            value_name="Rolling Value",
        )

        # Map the metric names to nicer labels
        metric_labels = {
            "rolling_result_vs_expectation": "Result vs Expectation",
            "rolling_other_9_players_quality_diff": "Other 9 Players Quality Diff",
            "rolling_teammate_quality": "Teammate Quality",
            "rolling_opp_quality": "Opponent Quality",
            "rolling_winner": "Winning Pct",
        }

        # Replace Metric names in the melted DataFrame
        df_melted["Metric"] = df_melted["Metric"].map(metric_labels)

        # Create line chart
        fig = px.line(
            df_melted,
            x="player_game_num",
            y="Rolling Value",
            color="Metric",
            hover_data=["rolling_date_range"],
            labels={
                "player_game_num": "Player Game Number",
                "rolling_date_range": "Dates",
                "Rolling Value": "Rolling Average",
            },
            title=f"{player_name}: {rolling_games}-Game Rolling Averages",
        )

        fig.update_layout(
            title=dict(
                text=f"{player_name}: {rolling_games}-Game Rolling Averages<br><sup>Double click on a metric to isolate it click to add others. Draw area to zoom.</sup>",
            ),
            xaxis_title="Player Game Number",
            yaxis_title="Rolling Values",
        )

        return fig
