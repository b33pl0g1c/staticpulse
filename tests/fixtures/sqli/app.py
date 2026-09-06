import sqlite3

def get_user(conn: sqlite3.Connection, user_id):
    cursor = conn.cursor()
    # Vulnerable: user_id is interpolated straight into SQL.
    query = "SELECT * FROM users WHERE id = '%s'" % user_id
    cursor.execute(query)
    return cursor.fetchone()
