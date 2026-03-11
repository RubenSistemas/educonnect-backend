from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(50), nullable=False)  # director, secretaria, profesor, estudiante
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    carnet = db.Column(db.String(50), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'role': self.role,
            'username': self.username,
            'first_name': self.first_name,
            'last_name': self.last_name,
            'carnet': self.carnet,
            'active': self.active
        }


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    area = db.Column(db.String(50), nullable=False, default='Humanística')
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    teacher = db.relationship('User', backref='subjects')

    def to_dict(self):
        teacher_name = None
        if self.teacher:
            teacher_name = f"{self.teacher.first_name} {self.teacher.last_name}"
        
        # Calculate how many students are enrolled in this subject
        enrolled_count = Enrollment.query.filter_by(subject_id=self.id).count() if self.id else 0
        
        return {
            'id': self.id,
            'name': self.name,
            'area': self.area,
            'teacher_id': self.teacher_id,
            'teacher_name': teacher_name,
            'enrolled_count': enrolled_count
        }


class Enrollment(db.Model):
    __tablename__ = 'enrollments'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    level = db.Column(db.String(50), nullable=False, default='Único')
    student = db.relationship('User', backref=db.backref('enrollments', lazy=True))
    subject = db.relationship('Subject', backref=db.backref('enrollments', lazy=True))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'subject_id': self.subject_id,
            'student_name': f"{self.student.first_name} {self.student.last_name}" if self.student else None,
            'student_carnet': self.student.carnet if self.student else None,
            'subject_name': self.subject.name if self.subject else None,
            'level': self.level,
            'created_at': self.created_at.strftime("%Y-%m-%d") if self.created_at else None,
        }


class StudentDocument(db.Model):
    __tablename__ = 'student_documents'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    document_name = db.Column(db.String(100), nullable=False)
    is_submitted = db.Column(db.Boolean, default=False)
    student = db.relationship('User', foreign_keys=[student_id], backref=db.backref('documents', lazy=True))

    def to_dict(self):
        return {
            'id': self.id,
            'student_id': self.student_id,
            'document_name': self.document_name,
            'is_submitted': self.is_submitted
        }


class SubjectMaterial(db.Model):
    __tablename__ = 'subject_materials'
    id = db.Column(db.Integer, primary_key=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    subject = db.relationship('Subject', backref=db.backref('materials', lazy=True))
    teacher = db.relationship('User', foreign_keys=[teacher_id])

    def to_dict(self):
        return {
            'id': self.id,
            'subject_id': self.subject_id,
            'title': self.title,
            'url': self.url
        }


class Grade(db.Model):
    __tablename__ = 'grades'
    id = db.Column(db.Integer, primary_key=True)
    enrollment_id = db.Column(db.Integer, db.ForeignKey('enrollments.id'), nullable=False)
    dimension = db.Column(db.String(50), nullable=False)  # ser, saber, decidir, hacer, autoevaluacion
    score = db.Column(db.Integer, default=0)
    enrollment = db.relationship('Enrollment', backref='grades')

    def to_dict(self):
        return {
            'id': self.id,
            'enrollment_id': self.enrollment_id,
            'dimension': self.dimension,
            'score': self.score
        }


class Communication(db.Model):
    __tablename__ = 'communications'
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', foreign_keys=[sender_id])
    receiver = db.relationship('User', foreign_keys=[receiver_id])


class Resource(db.Model):
    __tablename__ = 'resources'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    url = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)


class SupportTicket(db.Model):
    __tablename__ = 'support_tickets'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='Open')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


def create_default_accounts():
    default_users = [
        {"role": "director", "username": "director_admin.pruebas@educaruben.com",
         "first_name": "Admin", "last_name": "Pruebas", "carnet": "101010"},
        {"role": "secretaria", "username": "secretaria_ana.maria@educaruben.com",
         "first_name": "Ana", "last_name": "Maria", "carnet": "202020"},
        {"role": "profesor", "username": "profesor_juan.perez@educaruben.com",
         "first_name": "Juan", "last_name": "Perez", "carnet": "12345"},
        {"role": "profesor", "username": "profesor_ruben.condori@educaruben.com",
         "first_name": "RUBEN", "last_name": "CONDORI", "carnet": "99999"},
        {"role": "estudiante", "username": "estudiante_luis.gomez@educaruben.com",
         "first_name": "Luis", "last_name": "Gomez", "carnet": "54321"},
    ]
    for user_data in default_users:
        if not User.query.filter_by(username=user_data['username']).first():
            new_user = User(
                role=user_data['role'],
                username=user_data['username'],
                first_name=user_data['first_name'],
                last_name=user_data['last_name'],
                carnet=user_data['carnet']
            )
            new_user.set_password(user_data['carnet'])
            db.session.add(new_user)
    db.session.commit()

    # ── Especialidades oficiales del CEA ──
    all_specialties = [
        ('Sistemas Infom\u00e1ticos', 'T\u00e9cnica'),
        ('Belleza Integral', 'T\u00e9cnica'),
        ('Gastronomia', 'T\u00e9cnica'),
        ('Parvularia', 'T\u00e9cnica'),
        ('Fisioterapia', 'T\u00e9cnica'),
        ('Contabilidad Publica', 'T\u00e9cnica'),
        ('Veterinaria', 'T\u00e9cnica'),
        ('Matematicas', 'Human\u00edstica'),
        ('Lenguaje y Comunicacion', 'Human\u00edstica'),
        ('Ciencias Naturales', 'Human\u00edstica'),
        ('Ciencias Sociales', 'Human\u00edstica'),
    ]
    for name, area in all_specialties:
        if not Subject.query.filter_by(name=name).first():
            db.session.add(Subject(name=name, area=area, teacher_id=None))
    db.session.commit()

    # Demo enrollment for default student (only if no enrollments yet)
    student = User.query.filter_by(role='estudiante').first()
    if student and not Enrollment.query.filter_by(student_id=student.id).first():
        first_subject = Subject.query.first()
        if first_subject:
            enr = Enrollment(student_id=student.id, subject_id=first_subject.id, level='Ciclo de Aprendizajes Elementales')
            db.session.add(enr)
            db.session.commit()
            docs = [
                StudentDocument(student_id=student.id, document_name='Certificado de Nacimiento', is_submitted=True),
                StudentDocument(student_id=student.id, document_name='Fotocopia Carnet', is_submitted=False),
                StudentDocument(student_id=student.id, document_name='Libreta Anterior', is_submitted=False),
            ]
            db.session.add_all(docs)
            db.session.commit()
            db.session.commit()
