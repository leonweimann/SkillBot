import os
import sqlite3
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List
import logging

logger = logging.getLogger(__name__)


# region Database Exceptions

class DatabaseError(Exception):
    """Base exception for database operations"""
    pass


class UserNotFoundError(DatabaseError):
    """Raised when a user is not found in the database"""
    pass


class TeacherNotFoundError(DatabaseError):
    """Raised when a teacher is not found in the database"""
    pass


class StudentNotFoundError(DatabaseError):
    """Raised when a student is not found in the database"""
    pass


class ConnectionNotFoundError(DatabaseError):
    """Raised when a teacher-student connection is not found"""
    pass


class ArchiveNotFoundError(DatabaseError):
    """Raised when an archive is not found in the database"""
    pass

# endregion


# region DatabaseManager

class DatabaseManager:
    @staticmethod
    def __get_db_path(guild_id: int) -> str:
        return os.path.join(os.path.dirname(__file__), f'../../data/skillbot_{guild_id}.db')

    @staticmethod
    def _connect(guild_id: int) -> sqlite3.Connection:
        try:
            conn = sqlite3.connect(DatabaseManager.__get_db_path(guild_id))
            # Enable foreign key constraints
            conn.execute("PRAGMA foreign_keys = ON")
            return conn
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to connect to database for guild {guild_id}: {e}") from e

    @staticmethod
    def create_tables(guild_id: int):
        try:
            with DatabaseManager._connect(guild_id) as conn:
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
                        teaching_category INTEGER,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS students (
                        user_id INTEGER PRIMARY KEY,
                        major_id INTEGER,
                        customer_id INTEGER,
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
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS archive (
                        id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL UNIQUE
                    )
                ''')
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS dev_mode (
                        user_id INTEGER PRIMARY KEY,
                        is_active BOOLEAN NOT NULL DEFAULT 1,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                ''')
                conn.commit()
                logger.info(f"Database tables created successfully for guild {guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to create tables for guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to create database tables: {e}") from e

    @staticmethod
    def get_all_teaching_categories(guild_id: int) -> List[int]:
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT DISTINCT teaching_category FROM teachers WHERE teaching_category IS NOT NULL')
                return [int(row[0]) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get teaching categories for guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to retrieve teaching categories: {e}") from e

# endregion


# region User

@dataclass
class User:
    guild_id: int
    id: int
    real_name: Optional[str] = field(default=None)
    hours_in_class: float = field(default=0.0)

    def __post_init__(self):
        """Load user data from database after initialization"""
        self.load()

    def load(self):
        """Load user data from database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT real_name, hours_in_class FROM users WHERE id = ?', (self.id,))
                user = cursor.fetchone()
                if user:
                    self.real_name, self.hours_in_class = user[0], user[1]
                else:
                    # User doesn't exist in database yet
                    self.real_name, self.hours_in_class = None, 0.0
        except sqlite3.Error as e:
            logger.error(f"Failed to load user {self.id} from guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to load user data: {e}") from e

    def save(self):
        """Save user data to database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO users (id, real_name, hours_in_class)
                    VALUES (?, ?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                    real_name = excluded.real_name,
                    hours_in_class = excluded.hours_in_class
                ''', (self.id, self.real_name, self.hours_in_class))
                conn.commit()
                logger.debug(f"Saved user {self.id} to guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to save user {self.id} to guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to save user data: {e}") from e

    def delete(self):
        """Delete user from database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM users WHERE id = ?', (self.id,))
                if cursor.rowcount == 0:
                    raise UserNotFoundError(f"User {self.id} not found in guild {self.guild_id}")
                conn.commit()
                logger.info(f"Deleted user {self.id} from guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to delete user {self.id} from guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to delete user: {e}") from e

    def edit(self, real_name: Optional[str] = None, hours_in_class: Optional[float] = None):
        """Edit user attributes and save to database"""
        if real_name is not None:
            self.real_name = real_name
        if hours_in_class is not None:
            self.hours_in_class = hours_in_class
        self.save()

    @property
    def is_student(self) -> bool:
        """Check if user is a student"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM students WHERE user_id = ? LIMIT 1', (self.id,))
                return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Failed to check if user {self.id} is student in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to check student status: {e}") from e

    @property
    def is_teacher(self) -> bool:
        """Check if user is a teacher"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM teachers WHERE user_id = ? LIMIT 1', (self.id,))
                return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Failed to check if user {self.id} is teacher in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to check teacher status: {e}") from e

# endregion


# region Subuser

@dataclass
class Subuser(User):
    def __init__(self, guild_id: int, id: int, subuser_id: int,
                 real_name: Optional[str] = None, hours_in_class: float = 0.0):
        self.guild_id = guild_id
        self.id = id
        self.subuser_id = subuser_id
        self.real_name = real_name
        self.hours_in_class = hours_in_class
        self.__post_init__()

    def __post_init__(self):
        """Load user data and validate subuser_id"""
        # Validate subuser_id first
        if self.subuser_id <= 0:
            raise ValueError(f"subuser_id must be a positive integer, got: {self.subuser_id}")

        # Load user data manually since we skipped super().__post_init__()
        self.load()

    def save(self):
        """Save subuser relationship to database"""
        # Validate subuser_id before saving
        if self.subuser_id <= 0:
            raise ValueError(f"Cannot save subuser with invalid subuser_id: {self.subuser_id}")

        try:
            # Save the user data first
            super().save()

            # Then save the subuser relationship
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO subusers (user_id, subuser_id)
                    VALUES (?, ?)
                    ON CONFLICT (user_id, subuser_id) DO NOTHING
                ''', (self.id, self.subuser_id))
                conn.commit()
                logger.debug(f"Saved subuser relationship: {self.id} -> {self.subuser_id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to save subuser {self.subuser_id} for user {self.id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to save subuser relationship: {e}") from e

    def delete(self):
        """Delete subuser relationship from database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM subusers WHERE user_id = ? AND subuser_id = ?', (self.id, self.subuser_id))
                if cursor.rowcount == 0:
                    raise UserNotFoundError(f"Subuser relationship {self.id} -> {self.subuser_id} not found in guild {self.guild_id}")
                conn.commit()
                logger.info(f"Deleted subuser relationship: {self.id} -> {self.subuser_id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to delete subuser {self.subuser_id} for user {self.id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to delete subuser relationship: {e}") from e

    def edit(self, real_name: Optional[str] = None, hours_in_class: Optional[float] = None,
             subuser_id: Optional[int] = None):
        """Edit subuser attributes and save to database"""
        if real_name is not None:
            self.real_name = real_name
        if hours_in_class is not None:
            self.hours_in_class = hours_in_class
        if subuser_id is not None:
            # Validate new subuser_id
            if subuser_id <= 0:
                raise ValueError(f"subuser_id must be a positive integer, got: {subuser_id}")

            # Need to delete old relationship and create new one
            old_subuser_id = self.subuser_id
            try:
                with DatabaseManager._connect(self.guild_id) as conn:
                    cursor = conn.cursor()
                    cursor.execute('DELETE FROM subusers WHERE user_id = ? AND subuser_id = ?', (self.id, old_subuser_id))
                    self.subuser_id = subuser_id
                    conn.commit()
            except sqlite3.Error as e:
                logger.error(f"Failed to update subuser_id from {old_subuser_id} to {subuser_id}: {e}")
                raise DatabaseError(f"Failed to update subuser relationship: {e}") from e
        self.save()

    @staticmethod
    def get_all_subusers(guild_id: int, user_id: int) -> List['Subuser']:
        """Get all subusers for a given user"""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT subuser_id FROM subusers WHERE user_id = ?', (user_id,))
                result = []
                for row in cursor.fetchall():
                    subuser = Subuser(guild_id=guild_id, id=user_id, subuser_id=row[0])
                    subuser.load()  # Load user data manually
                    result.append(subuser)
                return result
        except sqlite3.Error as e:
            logger.error(f"Failed to get subusers for user {user_id} in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to retrieve subusers: {e}") from e

    @staticmethod
    def get_user_of_subuser(guild_id: int, subuser_id: int) -> Optional[User]:
        """Get the main user for a given subuser"""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM subusers WHERE subuser_id = ?', (subuser_id,))
                row = cursor.fetchone()
                if row:
                    return User(guild_id=guild_id, id=row[0])
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to get user for subuser {subuser_id} in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to retrieve user for subuser: {e}") from e

    @staticmethod
    def is_any_subuser(guild_id: int, subuser_id: int) -> bool:
        """Check if the given ID is a subuser of anyone"""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT 1 FROM subusers WHERE subuser_id = ? LIMIT 1', (subuser_id,))
                return cursor.fetchone() is not None
        except sqlite3.Error as e:
            logger.error(f"Failed to check if {subuser_id} is subuser in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to check subuser status: {e}") from e

# endregion


# region Teacher

@dataclass
class Teacher(User):
    subjects: Optional[str] = field(default=None)
    phonenumber: Optional[str] = field(default=None)
    availability: Optional[str] = field(default=None)
    teaching_category: Optional[int] = field(default=None)

    def __post_init__(self):
        """Load user and teacher data from database"""
        super().__post_init__()  # Load user data
        self.load_teacher()

    def load_teacher(self):
        """Load teacher-specific data from database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT subjects, phonenumber, availability, teaching_category FROM teachers WHERE user_id = ?', (self.id,))
                teacher = cursor.fetchone()
                if teacher:
                    self.subjects, self.phonenumber, self.availability, self.teaching_category = teacher
        except sqlite3.Error as e:
            logger.error(f"Failed to load teacher data for user {self.id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to load teacher data: {e}") from e

    def save(self):
        """Save user and teacher data to database"""
        try:
            super().save()  # Save user data first

            with DatabaseManager._connect(self.guild_id) as conn:
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
                logger.debug(f"Saved teacher {self.id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to save teacher {self.id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to save teacher data: {e}") from e

    def edit(self, real_name: Optional[str] = None, hours_in_class: Optional[float] = None,
             subjects: Optional[str] = None, phonenumber: Optional[str] = None,
             availability: Optional[str] = None, teaching_category: Optional[int] = None):
        """Edit teacher attributes and save to database"""
        if real_name is not None:
            self.real_name = real_name
        if hours_in_class is not None:
            self.hours_in_class = hours_in_class
        if subjects is not None:
            self.subjects = subjects
        if phonenumber is not None:
            self.phonenumber = phonenumber
        if availability is not None:
            self.availability = availability
        if teaching_category is not None:
            self.teaching_category = teaching_category
        self.save()

    def pop(self):
        """Remove teacher role from user (delete from teachers table)"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM teachers WHERE user_id = ?', (self.id,))
                if cursor.rowcount == 0:
                    raise TeacherNotFoundError(f"Teacher {self.id} not found in guild {self.guild_id}")
                conn.commit()
                logger.info(f"Removed teacher role from user {self.id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to remove teacher {self.id} from guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to remove teacher: {e}") from e

    def connect_student(self, student_id: int, channel_id: int):
        """Create a connection between this teacher and a student"""
        try:
            connection = TeacherStudentConnection(
                guild_id=self.guild_id,
                teacher_id=self.id,
                student_id=student_id,
                channel_id=channel_id
            )
            connection.save()
        except Exception as e:
            logger.error(f"Failed to connect teacher {self.id} with student {student_id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to create teacher-student connection: {e}") from e

# endregion


# region Student

@dataclass
class Student(User):
    major_id: Optional[int] = field(default=None)
    customer_id: Optional[int] = field(default=None)

    def __post_init__(self):
        """Load user and student data from database"""
        super().__post_init__()  # Load user data
        self.load_student()

    def load_student(self):
        """Load student-specific data from database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT major_id, customer_id FROM students WHERE user_id = ?', (self.id,))
                student = cursor.fetchone()
                if student:
                    self.major_id, self.customer_id = student
        except sqlite3.Error as e:
            logger.error(f"Failed to load student data for user {self.id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to load student data: {e}") from e

    def save(self):
        """Save user and student data to database"""
        try:
            super().save()  # Save user data first

            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO students (user_id, major_id, customer_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT (user_id) DO UPDATE SET
                    major_id = excluded.major_id,
                    customer_id = excluded.customer_id
                ''', (self.id, self.major_id, self.customer_id))
                conn.commit()
                logger.debug(f"Saved student {self.id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to save student {self.id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to save student data: {e}") from e

    def edit(self, real_name: Optional[str] = None, hours_in_class: Optional[float] = None,
             major_id: Optional[int] = None, customer_id: Optional[int] = None):
        """Edit student attributes and save to database"""
        if real_name is not None:
            self.real_name = real_name
        if hours_in_class is not None:
            self.hours_in_class = hours_in_class
        if major_id is not None:
            self.major_id = major_id
        if customer_id is not None:
            self.customer_id = customer_id
        self.save()

    def pop(self):
        """Remove student role from user (delete from students table and related connections)"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                # Delete related records first due to foreign key constraints
                cursor.execute('DELETE FROM teacher_student WHERE student_id = ?', (self.id,))
                cursor.execute('DELETE FROM students WHERE user_id = ?', (self.id,))
                if cursor.rowcount == 0:
                    raise StudentNotFoundError(f"Student {self.id} not found in guild {self.guild_id}")
                conn.commit()
                logger.info(f"Removed student role from user {self.id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to remove student {self.id} from guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to remove student: {e}") from e

    def connect_teacher(self, teacher_id: int, channel_id: int):
        """Create a connection between this student and a teacher"""
        try:
            connection = TeacherStudentConnection(
                guild_id=self.guild_id,
                teacher_id=teacher_id,
                student_id=self.id,
                channel_id=channel_id
            )
            connection.save()
        except Exception as e:
            logger.error(f"Failed to connect student {self.id} with teacher {teacher_id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to create teacher-student connection: {e}") from e

# endregion


# region TeacherStudentConnection

@dataclass
class TeacherStudentConnection:
    guild_id: int
    teacher_id: int
    student_id: int
    channel_id: int  # No default value - must be explicitly provided

    def __post_init__(self):
        """Load connection data and validate"""
        self.load()
        self._validate()

    def _validate(self):
        """Validate the connection data"""
        if self.teacher_id == self.student_id:
            raise ValueError("Teacher and student cannot be the same person")
        if self.channel_id <= 0:
            raise ValueError(f"Channel ID must be a positive integer, got: {self.channel_id}")

    def load(self):
        """Load connection data from database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT channel_id FROM teacher_student WHERE teacher_id = ? AND student_id = ?',
                               (self.teacher_id, self.student_id))
                connection = cursor.fetchone()
                if connection:
                    self.channel_id = connection[0]
        except sqlite3.Error as e:
            logger.error(f"Failed to load teacher-student connection {self.teacher_id}-{self.student_id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to load teacher-student connection: {e}") from e

    def save(self):
        """Save connection to database"""
        try:
            self._validate()  # Validate before saving

            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO teacher_student (teacher_id, student_id, channel_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT (teacher_id, student_id) DO UPDATE SET
                    channel_id = excluded.channel_id
                ''', (self.teacher_id, self.student_id, self.channel_id))
                conn.commit()
                logger.debug(f"Saved teacher-student connection {self.teacher_id}-{self.student_id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to save teacher-student connection {self.teacher_id}-{self.student_id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to save teacher-student connection: {e}") from e

    def delete(self):
        """Delete connection from database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM teacher_student WHERE teacher_id = ? AND student_id = ?',
                               (self.teacher_id, self.student_id))
                if cursor.rowcount == 0:
                    raise ConnectionNotFoundError(f"Teacher-student connection {self.teacher_id}-{self.student_id} not found in guild {self.guild_id}")
                conn.commit()
                logger.info(f"Deleted teacher-student connection {self.teacher_id}-{self.student_id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to delete teacher-student connection {self.teacher_id}-{self.student_id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to delete teacher-student connection: {e}") from e

    def edit(self, channel_id: Optional[int] = None):
        """Edit connection attributes and save to database"""
        if channel_id is not None:
            if channel_id <= 0:
                raise ValueError(f"Channel ID must be a positive integer, got: {channel_id}")
            self.channel_id = channel_id
        self.save()

    @staticmethod
    def find_by_student(guild_id: int, student_id: int) -> Optional['TeacherStudentConnection']:
        """Find connection by student ID"""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT teacher_id, student_id, channel_id FROM teacher_student WHERE student_id = ?', (student_id,))
                connection = cursor.fetchone()
                if connection:
                    return TeacherStudentConnection(
                        guild_id=guild_id,
                        teacher_id=connection[0],
                        student_id=connection[1],
                        channel_id=connection[2]
                    )
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to find connection for student {student_id} in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to find teacher-student connection: {e}") from e

    @staticmethod
    def find_by_teacher(guild_id: int, teacher_id: int) -> Optional['TeacherStudentConnection']:
        """Find connection by teacher ID"""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT teacher_id, student_id, channel_id FROM teacher_student WHERE teacher_id = ?', (teacher_id,))
                connection = cursor.fetchone()
                if connection:
                    return TeacherStudentConnection(
                        guild_id=guild_id,
                        teacher_id=connection[0],
                        student_id=connection[1],
                        channel_id=connection[2]
                    )
                return None
        except sqlite3.Error as e:
            logger.error(f"Failed to find connection for teacher {teacher_id} in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to find teacher-student connection: {e}") from e

# endregion


# region UserVoiceChannelJoin

@dataclass
class UserVoiceChannelJoin:
    guild_id: int
    user_id: int
    voice_channel_id: int
    join_time: datetime = field(default_factory=datetime.now)

    def save(self):
        """Save voice channel join record to database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO user_voice_channel_join (user_id, voice_channel_id, join_time)
                    VALUES (?, ?, ?)
                ''', (self.user_id, self.voice_channel_id, self.join_time))
                conn.commit()
                logger.debug(f"Saved voice channel join for user {self.user_id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to save voice channel join for user {self.user_id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to save voice channel join: {e}") from e

    def edit(self, voice_channel_id: Optional[int] = None, join_time: Optional[datetime] = None):
        """Edit voice channel join attributes and save to database"""
        if voice_channel_id is not None:
            self.voice_channel_id = voice_channel_id
        if join_time is not None:
            self.join_time = join_time
        self.save()

    @staticmethod
    def remove(guild_id: int, user_id: int):
        """Remove voice channel join record for user"""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM user_voice_channel_join WHERE user_id = ?', (user_id,))
                conn.commit()
                logger.debug(f"Removed voice channel join record for user {user_id} in guild {guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to remove voice channel join for user {user_id} in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to remove voice channel join: {e}") from e

    @staticmethod
    def get_join_time(guild_id: int, user_id: int) -> Optional[str]:
        """Get the join time for a user's voice channel session"""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT join_time FROM user_voice_channel_join WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                return result[0] if result else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get join time for user {user_id} in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to get voice channel join time: {e}") from e

    @staticmethod
    def transfer_hours(guild_id: int, user_id: int):
        """Transfer voice channel time to user's hours and remove the join record"""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT join_time FROM user_voice_channel_join WHERE user_id = ?', (user_id,))
                join_time = cursor.fetchone()
                if join_time:
                    join_time = datetime.strptime(join_time[0], '%Y-%m-%d %H:%M:%S')
                    time_in_class = (datetime.now() - join_time).total_seconds() / 3600.0
                    cursor.execute('UPDATE users SET hours_in_class = hours_in_class + ? WHERE id = ?', (time_in_class, user_id))
                    cursor.execute('DELETE FROM user_voice_channel_join WHERE user_id = ?', (user_id,))
                    conn.commit()
                    logger.info(f"Transferred {time_in_class:.2f} hours for user {user_id} in guild {guild_id}")
                else:
                    logger.warning(f"No voice channel join record found for user {user_id} in guild {guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to transfer hours for user {user_id} in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to transfer voice channel hours: {e}") from e

# endregion


# region Archive

@dataclass
class Archive:
    guild_id: int
    id: int
    name: Optional[str] = field(default=None)

    def __post_init__(self):
        """Load archive data from database"""
        self.load()

    def load(self):
        """Load archive data from database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT name FROM archive WHERE id = ?', (self.id,))
                archive = cursor.fetchone()
                if archive:
                    self.name = archive[0]
        except sqlite3.Error as e:
            logger.error(f"Failed to load archive {self.id} from guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to load archive data: {e}") from e

    def save(self):
        """Save archive data to database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO archive (id, name)
                    VALUES (?, ?)
                    ON CONFLICT (id) DO UPDATE SET
                    name = excluded.name
                ''', (self.id, self.name))
                conn.commit()
                logger.debug(f"Saved archive {self.id} in guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to save archive {self.id} in guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to save archive data: {e}") from e

    def edit(self, name: Optional[str] = None):
        """Edit archive name and save to database"""
        if name is not None:
            self.name = name
        self.save()

    def delete(self):
        """Delete archive from database"""
        try:
            with DatabaseManager._connect(self.guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM archive WHERE id = ?', (self.id,))
                if cursor.rowcount == 0:
                    raise ArchiveNotFoundError(f"Archive {self.id} not found in guild {self.guild_id}")
                conn.commit()
                logger.info(f"Deleted archive {self.id} from guild {self.guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to delete archive {self.id} from guild {self.guild_id}: {e}")
            raise DatabaseError(f"Failed to delete archive: {e}") from e

    @staticmethod
    def get_all(guild_id: int) -> List['Archive']:
        """Get all archives for a guild"""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM archive')
                return [Archive(guild_id=guild_id, id=row[0]) for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get all archives for guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to retrieve archives: {e}") from e

# endregion


# region DevMode

class DevMode:
    """Manages per-user developer mode settings."""

    @staticmethod
    def set_dev_mode(guild_id: int, user_id: int, is_active: bool):
        """Set dev mode status for a user."""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                if is_active:
                    cursor.execute('''
                        INSERT INTO dev_mode (user_id, is_active)
                        VALUES (?, ?)
                        ON CONFLICT (user_id) DO UPDATE SET is_active = excluded.is_active
                    ''', (user_id, True))
                else:
                    # If deactivating, remove the record entirely
                    cursor.execute('DELETE FROM dev_mode WHERE user_id = ?', (user_id,))
                conn.commit()
                logger.debug(f"Set dev mode to {is_active} for user {user_id} in guild {guild_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to set dev mode for user {user_id} in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to set dev mode: {e}") from e

    @staticmethod
    def is_dev_mode_active(guild_id: int, user_id: int) -> bool:
        """Check if dev mode is active for a user."""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT is_active FROM dev_mode WHERE user_id = ?', (user_id,))
                result = cursor.fetchone()
                return result[0] if result else False
        except sqlite3.Error as e:
            logger.error(f"Failed to check dev mode for user {user_id} in guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to check dev mode: {e}") from e

    @staticmethod
    def get_active_dev_users(guild_id: int) -> List[int]:
        """Get all users with active dev mode."""
        try:
            with DatabaseManager._connect(guild_id) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM dev_mode WHERE is_active = 1')
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Failed to get active dev users for guild {guild_id}: {e}")
            raise DatabaseError(f"Failed to get active dev users: {e}") from e

# endregion
