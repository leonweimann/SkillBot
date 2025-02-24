import os
import sqlite3
from datetime import datetime


# region DatabaseManager

DB_PATH = os.path.join(os.path.dirname(__file__), '../../data/new_skillbot.db')  # TODO: Change to skillbot.db


class DatabaseManager:
    @staticmethod
    def _connect() -> sqlite3.Connection:
        return sqlite3.connect(DB_PATH)

    @staticmethod
    def create_tables():
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    real_name TEXT DEFAULT NULL,
                    hours_in_class REAL NOT NULL DEFAULT 0.0
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subusers (
                    user_id INTEGER NOT NULL,
                    subuser_id INTEGER NOT NULL,
                    PRIMARY KEY (user_id, subuser_id),
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS teachers (
                    user_id INTEGER PRIMARY KEY,
                    subjects TEXT,
                    phonenumber TEXT,
                    availability TEXT,
                    teaching_category INTEGER NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS students (
                    user_id INTEGER PRIMARY KEY,
                    major TEXT,
                    customer_id TEXT UNIQUE,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS teacher_student (
                    teacher_id INTEGER NOT NULL,
                    student_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL UNIQUE,
                    PRIMARY KEY (teacher_id, student_id),
                    FOREIGN KEY (teacher_id) REFERENCES teachers (user_id),
                    FOREIGN KEY (student_id) REFERENCES students (user_id)
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

# endregion


# region User

class User:
    def __init__(self, user_id: int):
        self.id = user_id
        self.load()

    def load(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (self.id,))
            user = cursor.fetchone()
            if user:
                self.real_name, self.hours_in_class = user[1], user[2]
            else:
                self.real_name, self.hours_in_class = None, 0.0

    def save(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (id, real_name, hours_in_class)
                VALUES (?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                real_name = excluded.real_name,
                hours_in_class = excluded.hours_in_class
            ''', (self.id, self.real_name, self.hours_in_class))
            conn.commit()

    def delete(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM users WHERE id = ?', (self.id,))
            conn.commit()

    def edit(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.save()

    @property
    def is_student(self) -> bool:
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM students WHERE user_id = ?', (self.id,))
            return cursor.fetchone() is not None

    @property
    def is_teacher(self) -> bool:
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM teachers WHERE user_id = ?', (self.id,))
            return cursor.fetchone() is not None

# endregion


# region Subuser

class Subuser(User):
    def __init__(self, user_id: int, subuser_id: int):
        super().__init__(user_id)
        self.subuser_id = subuser_id

    def save(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO subusers (user_id, subuser_id)
                VALUES (?, ?)
                ON CONFLICT (user_id, subuser_id) DO NOTHING
            ''', (self.id, self.subuser_id))
            conn.commit()

    def delete(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM subusers WHERE user_id = ? AND subuser_id = ?', (self.id, self.subuser_id))
            conn.commit()

    @staticmethod
    def get_all_subusers(user_id: int) -> list['Subuser']:
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subusers WHERE user_id = ?', (user_id,))
            return [Subuser(user_id, row[1]) for row in cursor.fetchall()]

    @staticmethod
    def get_user_of_subuser(subuser_id: int) -> User | None:
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subusers WHERE subuser_id = ?', (subuser_id,))
            row = cursor.fetchone()
            if row:
                return User(row[0])
            return None

# endregion


# region Teacher

class Teacher(User):
    def __init__(self, user_id: int):
        super().__init__(user_id)
        self.subjects = None
        self.phonenumber = None
        self.availability = None
        self.teaching_category = None
        self.load_teacher()

    def load_teacher(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM teachers WHERE user_id = ?', (self.id,))
            teacher = cursor.fetchone()
            if teacher:
                self.subjects, self.phonenumber, self.availability, self.teaching_category = teacher[1], teacher[2], teacher[3], teacher[4]

    def save(self):
        super().save()
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO teachers (user_id, subjects, phonenumber, availability, teaching_category)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                subjects = excluded.subjects,
                phonenumber = excluded.phonenumber,
                availability = excluded.availability,
                teaching_category = excluded.teaching_category
            ''', (self.id, self.subjects, self.phonenumber, self.availability, self.teaching_category))
            conn.commit()

    def edit(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.save()

    def pop(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM teachers WHERE user_id = ?', (self.id,))
            conn.commit()

    def connect_student(self, student_id: int, channel_id: int):
        TeacherStudentConnection(self.id, student_id, channel_id).save()

# endregion


# region Student

class Student(User):
    def __init__(self, user_id: int):
        super().__init__(user_id)
        self.major = None
        self.customer_id = None
        self.load_student()

    def load_student(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM students WHERE user_id = ?', (self.id,))
            student = cursor.fetchone()
            if student:
                self.major, self.customer_id = student[1], student[2]

    def save(self):
        super().save()
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO students (user_id, major, customer_id)
                VALUES (?, ?, ?)
                ON CONFLICT (user_id) DO UPDATE SET
                major = excluded.major,
                customer_id = excluded.customer_id
            ''', (self.id, self.major, self.customer_id))
            conn.commit()

    def edit(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.save()

    def pop(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM students WHERE user_id = ?', (self.id,))
            conn.commit()
            cursor.execute('DELETE FROM teacher_student WHERE student_id = ?', (self.id,))
            conn.commit()

    def connect_teacher(self, teacher_id: int, channel_id: int):
        TeacherStudentConnection(teacher_id, self.id, channel_id=channel_id).save()

# endregion


# region TeacherStudentConnection

class TeacherStudentConnection:
    def __init__(self, teacher_id: int, student_id: int, channel_id: int = -1):
        self.teacher_id = teacher_id
        self.student_id = student_id
        self.channel_id = channel_id
        self.load()

    def __post_init__(self):
        assert self.teacher_id != self.student_id, "Teacher and student cannot be the same person"
        assert self.channel_id != -1, "Channel ID cannot be -1 / was not set / found"

    def load(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM teacher_student WHERE teacher_id = ? AND student_id = ?', (self.teacher_id, self.student_id))
            connection = cursor.fetchone()
            if connection:
                self.channel_id = connection[2]

    def save(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO teacher_student (teacher_id, student_id, channel_id)
                VALUES (?, ?, ?)
                ON CONFLICT (teacher_id, student_id) DO UPDATE SET
                channel_id = excluded.channel_id
            ''', (self.teacher_id, self.student_id, self.channel_id))
            conn.commit()

    def delete(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM teacher_student WHERE teacher_id = ? AND student_id = ?', (self.teacher_id, self.student_id))
            conn.commit()

    @staticmethod
    def find_by_student(student_id: int) -> 'TeacherStudentConnection | None':
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM teacher_student WHERE student_id = ?', (student_id,))
            connection = cursor.fetchone()
            if connection:
                return TeacherStudentConnection(connection[0], connection[1], connection[2])
            return None

    @staticmethod
    def find_by_teacher(teacher_id: int) -> 'TeacherStudentConnection | None':
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM teacher_student WHERE teacher_id = ?', (teacher_id,))
            connection = cursor.fetchone()
            if connection:
                return TeacherStudentConnection(connection[0], connection[1], connection[2])
            return None

# endregion


# region UserVoiceChannelJoin

class UserVoiceChannelJoin:
    def __init__(self, user_id: int, voice_channel_id: int):
        self.user_id = user_id
        self.voice_channel_id = voice_channel_id
        self.join_time = datetime.now()

    def save(self):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO user_voice_channel_join (user_id, voice_channel_id, join_time)
                VALUES (?, ?, ?)
            ''', (self.user_id, self.voice_channel_id, self.join_time))
            conn.commit()

    @staticmethod
    def remove(user_id: int):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM user_voice_channel_join WHERE user_id = ?', (user_id,))
            conn.commit()

    @staticmethod
    def get_join_time(user_id: int) -> str:
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT join_time FROM user_voice_channel_join WHERE user_id = ?', (user_id,))
            return cursor.fetchone()[0]

    @staticmethod
    def transfer_hours(user_id: int):
        with DatabaseManager._connect() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT join_time FROM user_voice_channel_join WHERE user_id = ?', (user_id,))
            join_time = cursor.fetchone()
            if join_time:
                join_time = datetime.strptime(join_time[0], '%Y-%m-%d %H:%M:%S')
                time_in_class = (datetime.now() - join_time).total_seconds() / 3600.0
                cursor.execute('UPDATE users SET hours_in_class = hours_in_class + ? WHERE id = ?', (time_in_class, user_id))
                cursor.execute('DELETE FROM user_voice_channel_join WHERE user_id = ?', (user_id,))
            conn.commit()

# endregion


if __name__ == '__main__':
    DatabaseManager.create_tables()
