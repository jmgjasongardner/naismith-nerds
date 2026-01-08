import duckdb


def create_tables(conn):
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS ratings (
        player VARCHAR,
        date VARCHAR,
        rating FLOAT,
        PRIMARY KEY (player, date)  -- Composite Primary Key
    );
    """
    )


if __name__ == "__main__":
    conn = duckdb.connect("bball_database.duckdb")
    create_tables(conn)
    conn.close()


# conn = duckdb.connect("bball_database.duckdb")
#
# # Delete unwanted players
# conn.execute("""
#     DELETE FROM ratings
#     WHERE player IN ('Name1', 'Name2');
# """)
#
# # Update a player name
# conn.execute("""
#     UPDATE ratings
#     SET player = 'WillS'
#     WHERE player = 'WWillStache';
# """)
#
# conn.close()
