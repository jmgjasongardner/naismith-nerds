import duckdb

def create_tables(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS ratings (
        player VARCHAR,
        date VARCHAR,
        rating FLOAT,
        PRIMARY KEY (player, date)  -- Composite Primary Key
    );
    """)

if __name__ == "__main__":
    conn = duckdb.connect('bball_database.duckdb')
    create_tables(conn)
    conn.close()
