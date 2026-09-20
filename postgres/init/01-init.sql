-- ==========================================
-- Student SQL Lab - Sample Database
-- ==========================================

CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150),
    age INTEGER
);

CREATE TABLE courses (
    id SERIAL PRIMARY KEY,
    course_name VARCHAR(100) NOT NULL,
    teacher VARCHAR(100)
);

CREATE TABLE enrollments (
    id SERIAL PRIMARY KEY,
    student_id INTEGER REFERENCES students(id),
    course_id INTEGER REFERENCES courses(id),
    grade INTEGER
);


-- ==========================================
-- Students
-- ==========================================

INSERT INTO students (name, email, age)
VALUES
('Alice Chan', 'alice@example.com', 18),
('Bob Wong', 'bob@example.com', 19),
('Charlie Lee', 'charlie@example.com', 18),
('Diana Ho', 'diana@example.com', 20),
('Eric Lam', 'eric@example.com', 19),
('Fiona Cheung', 'fiona@example.com', 18);


-- ==========================================
-- Courses
-- ==========================================

INSERT INTO courses (course_name, teacher)
VALUES
('Database Fundamentals', 'Mr Chan'),
('Web Development', 'Ms Lee'),
('Python Programming', 'Mr Wong'),
('Computer Science', 'Ms Ho');


-- ==========================================
-- Enrollments
-- ==========================================

INSERT INTO enrollments
(student_id, course_id, grade)
VALUES
(1, 1, 88),
(1, 2, 92),
(2, 1, 75),
(2, 3, 81),
(3, 1, 95),
(3, 2, 87),
(3, 3, 91),
(4, 2, 78),
(4, 4, 85),
(5, 1, 84),
(5, 3, 89),
(6, 1, 93),
(6, 4, 90);
