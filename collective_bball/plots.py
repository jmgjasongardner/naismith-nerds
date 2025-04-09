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
