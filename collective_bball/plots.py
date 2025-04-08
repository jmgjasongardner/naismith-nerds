import plotly
import polars as pl
import pandas as pd
import plotly.express as px
import plotly.io as pio
import numpy as np


class Plots:
    def __init__(self, conn):
        self.conn = conn  # Store the connection inside the class
        self.plot_ratings = None  # Placeholder for the plot

    def plot_ratings_time(self):
        # Fetch data from DuckDB and convert it to Polars
        df_pandas = self.conn.execute("SELECT * FROM ratings WHERE player NOT ILIKE '%tier%'").fetch_df()

        # Ensure 'date' is a datetime object for sorting
        df_pandas["date"] = pd.to_datetime(df_pandas["date"])
        fig = px.line(df_pandas, x="date", y="rating", color="player",
                      labels = {'x': "Date", 'y': "Rating"}, title="Player Ratings Over Time <br><sup>Double click on a player to filter to them and click to add others. Draw area to zoom.</sup>")
        # fig.show()

        self.plot_ratings = fig.to_html(full_html=False)

        return self.plot_ratings
