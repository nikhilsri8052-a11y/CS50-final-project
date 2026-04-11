import os
import sqlite3
path = 'database.db'
if not os.path.exists(path):
    print('NO_DB')
else:
    conn = sqlite3.connect(path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info('users');")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    conn.close()
