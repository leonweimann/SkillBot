from datetime import datetime
import os
import sqlite3


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
                    hours_in_class REAL NOT NULL DEFAULT 0.0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS teacher_student (
                    teacher_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL UNIQUE,
                    channel_id INTEGER NOT NULL UNIQUE,
                    PRIMARY KEY (teacher_id, student_id),
                    FOREIGN KEY (teacher_id) REFERENCES users (id),
                    FOREIGN KEY (student_id) REFERENCES users (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS user_voice_channel_join (
                    user_id INTEGER NOT NULL,
                    voice_channel_id INTEGER NOT NULL,
                    join_time TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, join_time),
                    FOREIGN KEY (user_id) REFERENCES users (id)
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
    def remove_user(user_id: int):
        DatabaseManager._execute('DELETE FROM users WHERE id = ?', user_id)

    # @staticmethod
    # def add_student_teacher(student_id: int, teacher_id: int):
    #     DatabaseManager._execute('INSERT OR IGNORE INTO teacher_student (teacher_id, student_id) VALUES (?, ?)', teacher_id, student_id)

    # @staticmethod
    # def remove_student_teacher(student_id: int):
    #     DatabaseManager._execute('DELETE FROM teacher_student WHERE student_id = ?', student_id)

    # @staticmethod
    # def get_student_teacher(student_id: int) -> int:  # Returns teacher_id
    #     return DatabaseManager._execute('SELECT teacher_id FROM teacher_student WHERE student_id = ?', student_id).fetchone()[0]

    @staticmethod
    def add_user_voice_channel_join(user_id: int, voice_channel_id: int):
        DatabaseManager._execute('INSERT INTO user_voice_channel_join (user_id, voice_channel_id, join_time) VALUES (?, ?, CURRENT_TIMESTAMP)', user_id, voice_channel_id)

    @staticmethod
    def remove_user_voice_channel_join(user_id: int):
        DatabaseManager._execute('DELETE FROM user_voice_channel_join WHERE user_id = ?', user_id)

    @staticmethod
    def get_user_voice_channel_join(user_id: int) -> str:  # Returns the join_time
        return DatabaseManager._execute('SELECT join_time FROM user_voice_channel_join WHERE user_id = ?', user_id).fetchone()[0]

    @staticmethod
    def transfer_hours_in_class_from_user_voice_channel_join(user_id: int):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT join_time FROM user_voice_channel_join WHERE user_id = ?
            ''', (user_id,))
            join_time = cursor.fetchone()
            if join_time:
                join_time = datetime.strptime(join_time[0], '%Y-%m-%d %H:%M:%S')
                time_in_class = (datetime.now() - join_time).total_seconds() / 3600.0
                cursor.execute('''
                    UPDATE users SET hours_in_class = hours_in_class + ? WHERE id = ?
                ''', (time_in_class, user_id))
                cursor.execute('''
                    DELETE FROM user_voice_channel_join WHERE user_id = ?
                ''', (user_id,))
            conn.commit()


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
            self.hours_in_class = 0.0

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

    @property
    def teacher_id(self) -> int | None:
        if self.user_type == 'student':
            return TeacherStudentConnection(self.id).teacher_id
        return None

    def save_voice_channel_join(self, voice_channel_id: int):
        DatabaseManager.add_user_voice_channel_join(self.id, voice_channel_id)

    def remove_voice_channel_join(self):
        DatabaseManager.remove_user_voice_channel_join(self.id)

    def get_voice_channel_join(self) -> str:
        return DatabaseManager.get_user_voice_channel_join(self.id)

    def transfer_hours_in_class_from_user_voice_channel_join(self):
        DatabaseManager.transfer_hours_in_class_from_user_voice_channel_join(self.id)


class TeacherStudentConnection:
    def __init__(self, student_id: int):
        self.student_id = student_id
        self.load()

    def load(self):
        if ts_con := DatabaseManager._execute('SELECT * FROM teacher_student WHERE student_id = ?', self.student_id).fetchone():
            (
                self.teacher_id,
                _,
                self.channel_id
            ) = ts_con
        else:
            self.teacher_id = None
            self.channel_id = None

    def save(self):
        DatabaseManager._execute('''
            INSERT INTO teacher_student (teacher_id, student_id, channel_id)
            VALUES (?, ?, ?)
            ON CONFLICT (student_id) DO UPDATE SET
            teacher_id = excluded.teacher_id,
            channel_id = excluded.channel_id
        ''', self.teacher_id, self.student_id, self.channel_id)

    def edit(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.save()

    def remove(self):
        DatabaseManager._execute('DELETE FROM teacher_student WHERE student_id = ?', self.student_id)


match __name__:
    case 'Utils.database':
        DatabaseManager._create_tables()

    case '__main__':
        DatabaseManager._create_tables()

        student = DBUser(2424242424)
        student.edit(user_type='student', icon='🎒', real_name='Ben Werner (TEST)')
        teacher = DBUser(4242424242)
        teacher.edit(user_type='teacher', icon='🎓', real_name='Leon Weimann (TEST)')
        ts_con = TeacherStudentConnection(student.id)
        ts_con.edit(teacher_id=teacher.id, channel_id=33333333)

        print(student.__dict__, teacher.__dict__, sep='\n', end='\n\n')
