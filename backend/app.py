import os, sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, Field

DB=os.getenv("DATABASE_PATH","school.db")
SECRET=os.getenv("JWT_SECRET","CHANGE_THIS_SECRET_BEFORE_DEPLOYMENT")
ALGORITHM="HS256"
pwd=CryptContext(schemes=["bcrypt"], deprecated="auto")
auth=HTTPBearer()
app=FastAPI(title="Online School API", version="1.0.0")
origins=os.getenv("CORS_ORIGINS","http://localhost:8000,http://127.0.0.1:8000").split(",")
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

def db():
    con=sqlite3.connect(DB); con.row_factory=sqlite3.Row
    return con

def init():
    c=db()
    c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL, password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','teacher','student')), created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS courses(id INTEGER PRIMARY KEY, title TEXT NOT NULL, description TEXT DEFAULT '', teacher_id INTEGER REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS grades(id INTEGER PRIMARY KEY, student_id INTEGER REFERENCES users(id), course_id INTEGER REFERENCES courses(id), value REAL NOT NULL, comment TEXT DEFAULT '', created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS attendance(id INTEGER PRIMARY KEY, student_id INTEGER REFERENCES users(id), course_id INTEGER REFERENCES courses(id), lesson_date TEXT NOT NULL, status TEXT NOT NULL, note TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS lessons(id INTEGER PRIMARY KEY, course_id INTEGER REFERENCES courses(id), title TEXT NOT NULL, starts_at TEXT NOT NULL, duration INTEGER DEFAULT 60, meeting_url TEXT DEFAULT '');
    CREATE TABLE IF NOT EXISTS assignments(id INTEGER PRIMARY KEY, course_id INTEGER REFERENCES courses(id), title TEXT NOT NULL, description TEXT DEFAULT '', due_date TEXT DEFAULT '');
    """)
    if not c.execute("SELECT id FROM users WHERE username='admin'").fetchone():
        # Initial credentials requested by the owner; change immediately after first login.
        c.execute("INSERT INTO users(username,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",("admin","Администратор школы",pwd.hash(os.getenv("ADMIN_PASSWORD","admin")),"admin",datetime.now(timezone.utc).isoformat()))
    c.commit(); c.close()
init()

class Login(BaseModel):
    username:str
    password:str
class UserCreate(BaseModel):
    username:str=Field(min_length=3,max_length=50)
    password:str=Field(min_length=8)
    full_name:str
    role:str
class CourseCreate(BaseModel):
    title:str
    description:str=""
    teacher_id:Optional[int]=None
class GradeCreate(BaseModel):
    student_id:int
    course_id:int
    value:float=Field(ge=1,le=100)
    comment:str=""
class AttendanceCreate(BaseModel):
    student_id:int
    course_id:int
    lesson_date:str
    status:str
    note:str=""
class LessonCreate(BaseModel):
    course_id:int
    title:str
    starts_at:str
    duration:int=60
    meeting_url:str=""
class AssignmentCreate(BaseModel):
    course_id:int
    title:str
    description:str=""
    due_date:str=""

def current_user(creds:HTTPAuthorizationCredentials=Depends(auth)):
    try:
        data=jwt.decode(creds.credentials,SECRET,algorithms=[ALGORITHM])
        c=db(); row=c.execute("SELECT id,username,full_name,role FROM users WHERE id=?",(data["sub"],)).fetchone(); c.close()
        if not row: raise HTTPException(401,"Пользователь не найден")
        return dict(row)
    except (JWTError,KeyError,ValueError): raise HTTPException(401,"Недействительный токен")
def require(*roles):
    def check(user=Depends(current_user)):
        if user["role"] not in roles: raise HTTPException(403,"Недостаточно прав")
        return user
    return check
def rows(sql,args=()):
    c=db(); result=[dict(x) for x in c.execute(sql,args).fetchall()]; c.close(); return result
def insert(sql,args):
    c=db()
    try:
        cur=c.execute(sql,args); c.commit(); return cur.lastrowid
    finally: c.close()

@app.get("/api/health")
def health(): return {"status":"ok","service":"online-school"}
@app.post("/api/auth/login")
def login(data:Login):
    c=db(); u=c.execute("SELECT * FROM users WHERE username=?",(data.username,)).fetchone(); c.close()
    if not u or not pwd.verify(data.password,u["password_hash"]): raise HTTPException(401,"Неверный логин или пароль")
    token=jwt.encode({"sub":str(u["id"]),"exp":datetime.now(timezone.utc)+timedelta(hours=12)},SECRET,algorithm=ALGORITHM)
    return {"access_token":token,"token_type":"bearer","user":{"id":u["id"],"username":u["username"],"full_name":u["full_name"],"role":u["role"]}}
@app.get("/api/auth/me")
def me(user=Depends(current_user)): return user
@app.post("/api/users")
def create_user(x:UserCreate,admin=Depends(require("admin"))):
    if x.role not in ("student","teacher","admin"): raise HTTPException(400,"Недопустимая роль")
    try:
        uid=insert("INSERT INTO users(username,full_name,password_hash,role,created_at) VALUES(?,?,?,?,?)",(x.username,x.full_name,pwd.hash(x.password),x.role,datetime.now(timezone.utc).isoformat()))
    except sqlite3.IntegrityError: raise HTTPException(409,"Логин уже занят")
    return {"id":uid,"username":x.username,"full_name":x.full_name,"role":x.role}
@app.get("/api/users")
def users(admin=Depends(require("admin","teacher"))):
    return rows("SELECT id,username,full_name,role,created_at FROM users ORDER BY full_name")
@app.get("/api/courses")
def courses(user=Depends(current_user)):
    if user["role"]=="student":
        return rows("SELECT DISTINCT c.* FROM courses c JOIN grades g ON g.course_id=c.id WHERE g.student_id=?",(user["id"],))
    return rows("SELECT * FROM courses ORDER BY title")
@app.post("/api/courses")
def create_course(x:CourseCreate,admin=Depends(require("admin"))):
    return {"id":insert("INSERT INTO courses(title,description,teacher_id) VALUES(?,?,?)",(x.title,x.description,x.teacher_id))}
@app.get("/api/grades")
def grades(user=Depends(current_user)):
    sql="SELECT g.*,u.full_name AS student_name,c.title AS course_title FROM grades g JOIN users u ON u.id=g.student_id JOIN courses c ON c.id=g.course_id"
    return rows(sql+" WHERE g.student_id=? ORDER BY g.created_at DESC",(user["id"],)) if user["role"]=="student" else rows(sql+" ORDER BY g.created_at DESC")
@app.post("/api/grades")
def add_grade(x:GradeCreate,teacher=Depends(require("admin","teacher"))):
    return {"id":insert("INSERT INTO grades(student_id,course_id,value,comment,created_at) VALUES(?,?,?,?,?)",(x.student_id,x.course_id,x.value,x.comment,datetime.now(timezone.utc).isoformat()))}
@app.get("/api/attendance")
def attendance(user=Depends(current_user)):
    sql="SELECT a.*,u.full_name AS student_name,c.title AS course_title FROM attendance a JOIN users u ON u.id=a.student_id JOIN courses c ON c.id=a.course_id"
    return rows(sql+" WHERE a.student_id=? ORDER BY lesson_date DESC",(user["id"],)) if user["role"]=="student" else rows(sql+" ORDER BY lesson_date DESC")
@app.post("/api/attendance")
def add_attendance(x:AttendanceCreate,teacher=Depends(require("admin","teacher"))):
    if x.status not in ("present","absent","late","excused"): raise HTTPException(400,"Недопустимый статус")
    return {"id":insert("INSERT INTO attendance(student_id,course_id,lesson_date,status,note) VALUES(?,?,?,?,?)",(x.student_id,x.course_id,x.lesson_date,x.status,x.note))}
@app.get("/api/lessons")
def lessons(user=Depends(current_user)): return rows("SELECT l.*,c.title AS course_title FROM lessons l JOIN courses c ON c.id=l.course_id ORDER BY starts_at")
@app.post("/api/lessons")
def add_lesson(x:LessonCreate,admin=Depends(require("admin","teacher"))):
    return {"id":insert("INSERT INTO lessons(course_id,title,starts_at,duration,meeting_url) VALUES(?,?,?,?,?)",(x.course_id,x.title,x.starts_at,x.duration,x.meeting_url))}
@app.get("/api/assignments")
def assignments(user=Depends(current_user)): return rows("SELECT a.*,c.title AS course_title FROM assignments a JOIN courses c ON c.id=a.course_id ORDER BY due_date")
@app.post("/api/assignments")
def add_assignment(x:AssignmentCreate,admin=Depends(require("admin","teacher"))):
    return {"id":insert("INSERT INTO assignments(course_id,title,description,due_date) VALUES(?,?,?,?)",(x.course_id,x.title,x.description,x.due_date))}
@app.get("/api/dashboard")
def dashboard(user=Depends(current_user)):
    if user["role"]=="student":
        return {"grades":len(rows("SELECT id FROM grades WHERE student_id=?",(user["id"],))),"attendance":len(rows("SELECT id FROM attendance WHERE student_id=?",(user["id"],))),"courses":len(rows("SELECT DISTINCT course_id FROM grades WHERE student_id=?",(user["id"],)))}
    return {"students":len(rows("SELECT id FROM users WHERE role='student'")),"teachers":len(rows("SELECT id FROM users WHERE role='teacher'")),"courses":len(rows("SELECT id FROM courses")),"lessons":len(rows("SELECT id FROM lessons"))}
