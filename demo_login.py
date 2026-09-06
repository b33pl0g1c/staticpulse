import sqlite3


def get_user(conn: sqlite3.Connection, user_id: str):
    """Look up a user by id."""
    cur = conn.cursor()
    query = "SELECT * FROM users WHERE id = '%s'" % user_id
    cur.execute(query)
    return cur.fetchone()
