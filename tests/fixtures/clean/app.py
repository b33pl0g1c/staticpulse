import sqlite3

def get_user(conn: sqlite3.Connection, user_id):
    cursor = conn.cursor()
    # Safe: parameterized query.
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()
