import sqlite3
import os


class DatabaseManager:
    @staticmethod
    def _connect() -> sqlite3.Connection:
        DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/skillbot.db')
        return sqlite3.connect(DB_PATH)

    @staticmethod
    def _create_tables():
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    real_name TEXT DEFAULT NULL,
                    icon TEXT DEFAULT NULL,
                    user_type TEXT CHECK(user_type IN ('admin', 'teacher', 'student')) DEFAULT NULL,
                    hours_in_class INTEGER NOT NULL DEFAULT 0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS teacher_student (
                    teacher_id TEXT NOT NULL,
                    student_id TEXT NOT NULL,
                    PRIMARY KEY (teacher_id, student_id),
                    FOREIGN KEY (teacher_id) REFERENCES users (id),
                    FOREIGN KEY (student_id) REFERENCES users (id)
                )
            ''')
            conn.commit()

    @staticmethod
    def _execute(query: str, *args):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute(query, args)
            conn.commit()
            return cursor


class DBUser:
    def __init__(self, discord_id: int):
        self.id = discord_id
        self.load()

    def load(self):
        if user := DatabaseManager._execute('SELECT * FROM users WHERE id = ?', self.id).fetchone():
            (
                _,
                self.real_name,
                self.icon,
                self.user_type,
                self.hours_in_class
            ) = user
        else:
            self.real_name = None
            self.icon = None
            self.user_type = None
            self.hours_in_class = 0

    def save(self):
        DatabaseManager._execute('''
            INSERT INTO users (id, real_name, icon, user_type, hours_in_class)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (id) DO UPDATE SET
            real_name = excluded.real_name,
            icon = excluded.icon,
            user_type = excluded.user_type,
            hours_in_class = excluded.hours_in_class
        ''', self.id, self.real_name, self.icon, self.user_type, self.hours_in_class)

    def edit(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.save()


if __name__ == '__main__':
    DatabaseManager._create_tables()
    user = DBUser(1234567890)
    user.edit(user_type='teacher', icon='🎓', real_name='Leon Weimann')
    print(user.__dict__)
