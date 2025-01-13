import sqlite3
import os


def create_connection():
    db_path = os.path.join(os.path.dirname(__file__), '../../data/skillbot.db')
    return sqlite3.connect(db_path)


def create_tables():
    with create_connection() as connection:
        cursor = connection.cursor()
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            discord_id TEXT NOT NULL UNIQUE,
            username TEXT NOT NULL,
            discriminator TEXT NOT NULL,
            real_name TEXT,
            hours_in_class INTEGER DEFAULT 0,
            icon TEXT,
            user_type TEXT CHECK(user_type IN ('teacher', 'student')) NOT NULL
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS channels (
            id INTEGER PRIMARY KEY,
            discord_id TEXT NOT NULL UNIQUE,
            user_id INTEGER,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        ''')
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS teacher_student (
            teacher_id INTEGER,
            student_id INTEGER,
            PRIMARY KEY (teacher_id, student_id),
            FOREIGN KEY (teacher_id) REFERENCES users (id),
            FOREIGN KEY (student_id) REFERENCES users (id)
        )
        ''')
        connection.commit()


def execute_query(query, params=(), connection=None, fetchone=False, fetchall=False):
    close_conn = False
    if connection is None:
        connection = create_connection()
        close_conn = True
    cursor = connection.cursor()
    cursor.execute(query, params)
    result = None
    if fetchone:
        result = cursor.fetchone()
    elif fetchall:
        result = cursor.fetchall()
    else:
        connection.commit()
    if close_conn:
        connection.close()
    return result


def add_user(discord_id, username, discriminator, real_name, icon, user_type, connection=None):
    query = '''
    INSERT INTO users (discord_id, username, discriminator, real_name, icon, user_type)
    VALUES (?, ?, ?, ?, ?, ?)
    '''
    execute_query(query, (discord_id, username, discriminator, real_name, icon, user_type), connection)


def get_user(discord_id, connection=None):
    query = 'SELECT * FROM users WHERE discord_id = ?'
    return execute_query(query, (discord_id,), connection, fetchone=True)


def update_user_hours(discord_id, hours, connection=None):
    query = 'UPDATE users SET hours_in_class = ? WHERE discord_id = ?'
    execute_query(query, (hours, discord_id), connection)


def update_user_icon(discord_id, icon, connection=None):
    query = 'UPDATE users SET icon = ? WHERE discord_id = ?'
    execute_query(query, (icon, discord_id), connection)


def add_channel(discord_id, user_id, connection=None):
    query = 'INSERT INTO channels (discord_id, user_id) VALUES (?, ?)'
    execute_query(query, (discord_id, user_id), connection)


def get_channels(user_id, connection=None):
    query = 'SELECT * FROM channels WHERE user_id = ?'
    return execute_query(query, (user_id,), connection, fetchall=True)


def assign_student_to_teacher(teacher_id, student_id, connection=None):
    query = 'INSERT INTO teacher_student (teacher_id, student_id) VALUES (?, ?)'
    execute_query(query, (teacher_id, student_id), connection)


def get_students_of_teacher(teacher_id, connection=None):
    query = 'SELECT student_id FROM teacher_student WHERE teacher_id = ?'
    return execute_query(query, (teacher_id,), connection, fetchall=True)


def get_teacher_of_student(student_id, connection=None):
    query = 'SELECT teacher_id FROM teacher_student WHERE student_id = ?'
    return execute_query(query, (student_id,), connection, fetchone=True)


# Call create_tables to ensure the tables are created when the module is imported
create_tables()