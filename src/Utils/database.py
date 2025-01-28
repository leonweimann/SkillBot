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
                    teacher_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL UNIQUE,
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

    @staticmethod
    def add_student_teacher(student_id: int, teacher_id: int):
        DatabaseManager._execute('INSERT OR IGNORE INTO teacher_student (teacher_id, student_id) VALUES (?, ?)', teacher_id, student_id)

    @staticmethod
    def remove_student_teacher(student_id: int):
        DatabaseManager._execute('DELETE FROM teacher_student WHERE student_id = ?', student_id)

    @staticmethod
    def get_student_teacher(student_id: int) -> int:  # Returns teacher_id
        return DatabaseManager._execute('SELECT teacher_id FROM teacher_student WHERE student_id = ?', student_id).fetchone()[0]


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


match __name__:
    case 'Utils.database':
        DatabaseManager._create_tables()

    case '__main__':
        DatabaseManager._create_tables()

        student = DBUser(2424242424)
        student.edit(user_type='student', icon='🎒', real_name='Ben Werner (TEST)')
        teacher = DBUser(4242424242)
        teacher.edit(user_type='teacher', icon='🎓', real_name='Leon Weimann (TEST)')
        DatabaseManager.add_student_teacher(student.id, teacher.id)

        print(student.__dict__, teacher.__dict__, sep='\n', end='\n\n')
