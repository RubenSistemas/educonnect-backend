from flask import request, jsonify
from app import app
from models import db, User, Subject, Enrollment, Grade, Communication, Resource, SupportTicket, StudentDocument, SubjectMaterial
import jwt
import datetime
from functools import wraps
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            parts = request.headers['Authorization'].split()
            if len(parts) == 2 and parts[0] == 'Bearer':
                token = parts[1]
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.query.filter_by(id=data['id']).first()
        except Exception as e:
            return jsonify({'message': 'Token is invalid!', 'error': str(e)}), 401
        return f(current_user, *args, **kwargs)
    return decorated
# ─── AUTH ────────────────────────────────────────────────────────────────────
@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Could not verify'}), 401
    user = User.query.filter_by(username=data['username']).first()
    if not user:
        return jsonify({'message': 'User not found'}), 401
    if user.check_password(data['password']):
        token = jwt.encode({
            'id': user.id,
            'role': user.role,
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        return jsonify({'token': token, 'user': user.to_dict()})
    return jsonify({'message': 'Invalid credentials'}), 401
@app.route('/api/profile/password', methods=['PUT'])
@token_required
def change_password(current_user):
    data = request.get_json()
    if not data or not data.get('new_password'):
        return jsonify({'message': 'New password is required'}), 400
    current_user.set_password(data['new_password'])
    db.session.commit()
    return jsonify({'message': 'Password updated successfully'})
# ─── DIRECTOR ────────────────────────────────────────────────────────────────
@app.route('/api/director/stats', methods=['GET'])
@token_required
def director_stats(current_user):
    if current_user.role != 'director':
        return jsonify({'message': 'Unauthorized'}), 403
    return jsonify({
        'total_users': User.query.count(),
        'teachers': User.query.filter_by(role='profesor').count(),
        'students': User.query.filter_by(role='estudiante').count(),
        'subjects': Subject.query.count()
    })
@app.route('/api/director/personnel', methods=['GET'])
@token_required
def get_personnel(current_user):
    if current_user.role != 'director':
        return jsonify({'message': 'Unauthorized'}), 403
    personnel = User.query.filter(User.role.in_(['profesor', 'secretaria'])).all()
    results = []
    for p in personnel:
        d = p.to_dict()
        if p.role == 'profesor':
            subject = Subject.query.filter_by(teacher_id=p.id).first()
            if subject:
                d['especialidad'] = 'EDUCACION PRIMARIA DE ADULTOS' if subject.name == 'Sin especialidad' else subject.name
                d['area'] = subject.area
                d['nivel'] = subject.level
            else:
                d['especialidad'] = "No asignado"
                d['area'] = None
                d['nivel'] = None
        results.append(d)
    return jsonify(results)
# Los anuncios se manejan al final con /api/announcement
# ─── SUBJECTS (Director & Secretaria) ─────────────────────────────────────────
@app.route('/api/subjects', methods=['GET'])
@token_required
def get_all_subjects(current_user):
    """Lista todas las materias con docente asignado."""
    if current_user.role not in ['director', 'secretaria', 'profesor']:
        return jsonify({'message': 'Unauthorized'}), 403
    subjects = Subject.query.all()
    return jsonify([s.to_dict() for s in subjects])
@app.route('/api/subjects', methods=['POST'])
@token_required
def create_subject(current_user):
    """Crear una nueva materia (director o secretaria)."""
    if current_user.role not in ['director', 'secretaria']:
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    if not data or not data.get('name') or not data.get('area'):
        return jsonify({'message': 'Subject name and area are required'}), 400
    teacher_id = data.get('teacher_id')
    if teacher_id:
        # Clear previous assignments for this teacher
        Subject.query.filter_by(teacher_id=teacher_id).update({"teacher_id": None})
    
    subject = Subject(name=data['name'], area=data['area'], teacher_id=teacher_id)
    db.session.add(subject)
    db.session.commit()
    return jsonify({'message': 'Materia creada exitosamente', 'subject': subject.to_dict()}), 201
@app.route('/api/subjects/<int:subject_id>/assign', methods=['PUT'])
@token_required
def assign_teacher(current_user, subject_id):
    """Asignar un docente a una materia."""
    if current_user.role not in ['director', 'secretaria']:
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    teacher_id = data.get('teacher_id')
    subject = Subject.query.get_or_404(subject_id)
    if teacher_id:
        teacher = User.query.filter_by(id=teacher_id, role='profesor').first()
        if not teacher:
            return jsonify({'message': 'Teacher not found'}), 404
        # Clear previous assignments for this teacher
        Subject.query.filter_by(teacher_id=teacher_id).update({"teacher_id": None})
    
    subject.teacher_id = teacher_id
    db.session.commit()
    return jsonify({'message': 'Docente asignado exitosamente', 'subject': subject.to_dict()})
@app.route('/api/subjects/<int:subject_id>/students', methods=['GET'])
@token_required
def get_enrolled_students(current_user, subject_id):
    """Obtener lista de estudiantes inscritos en una materia (secretaria / director)."""
    if current_user.role not in ['director', 'secretaria']:
        return jsonify({'message': 'Unauthorized'}), 403
    subject = Subject.query.get_or_404(subject_id)
    enrollments = Enrollment.query.filter_by(subject_id=subject_id).all()
    return jsonify({
        'subject': subject.to_dict(),
        'students': [e.to_dict() for e in enrollments],
        'total': len(enrollments)
    })
# ─── SECRETARY ────────────────────────────────────────────────────────────────
@app.route('/api/secretaria/users', methods=['POST'])
@token_required
def create_user(current_user):
    if current_user.role not in ['secretaria', 'director']:
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    
    # Generate the email username cleanly
    first_name = data.get('first_name', '').strip()
    last_name = data.get('last_name', '').strip()
    raw_username = f"{first_name}{last_name}@educonnect.com".lower()
    username = raw_username.replace(" ", "")
    
    if not username or username == "@educonnect.com":
        return jsonify({'message': 'First name and last name are required to generate username'}), 400
        
    if User.query.filter_by(username=username).first():
        return jsonify({'message': f'Username {username} already exists'}), 400
        
    new_user = User(
        role=data['role'],
        username=username,
        first_name=first_name,
        last_name=last_name,
        carnet=data['carnet']
    )
    new_user.set_password(data['carnet'])
    db.session.add(new_user)
    db.session.commit()
    return jsonify({'message': 'User created successfully', 'user': new_user.to_dict()})

@app.route('/api/secretaria/users_grouped', methods=['GET'])
@token_required
def get_users_grouped(current_user):
    """Returns all users grouped by: Administrativos, Docentes, Estudiantes Técnica, Estudiantes Humanística."""
    if current_user.role not in ['secretaria', 'director']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    all_users = User.query.all()
    groups = {
        'administrativos': [],
        'docentes': [],
        'tecnicos': [],
        'humanisticos': []
    }
    
    for u in all_users:
        entry = {
            'id': u.id,
            'nombre': f"{u.first_name} {u.last_name}",
            'correo': u.username,
            'carnet': u.carnet,
            'role': u.role
        }
        if u.role in ['director', 'secretaria']:
            groups['administrativos'].append(entry)
        elif u.role == 'profesor':
            # Get all their assigned subjects
            subjects = Subject.query.filter_by(teacher_id=u.id).all()
            entry['asignaciones'] = [
                {'especialidad': s.name, 'area': s.area, 'nivel': s.level} 
                for s in subjects
            ]
            # Keep these for single-subject compatibility
            if subjects:
                entry['especialidad'] = subjects[0].name
                entry['area'] = subjects[0].area
                entry['nivel'] = subjects[0].level
            groups['docentes'].append(entry)
        elif u.role == 'estudiante':
            # Look up their enrollment area
            enr = Enrollment.query.filter_by(student_id=u.id).first()
            if enr and enr.subject and enr.subject.area == 'Técnica':
                groups['tecnicos'].append(entry)
            else:
                # Default to Humanística if no enrollment or humanística area
                groups['humanisticos'].append(entry)
    
    return jsonify(groups)


@app.route('/api/users', methods=['GET'])
@token_required
def get_users(current_user):
    if current_user.role not in ['director', 'secretaria', 'profesor']:
        return jsonify({'message': 'Unauthorized'}), 403
    role_filter = request.args.get('role')
    if role_filter:
        users = User.query.filter_by(role=role_filter).all()
    else:
        users = User.query.all()
    return jsonify([user.to_dict() for user in users])
@app.route('/api/users/<int:uid>/password', methods=['PUT'])
@token_required
def update_password(current_user, uid):
    if current_user.id != uid:
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    old_pw = data.get('old_password')
    new_pw = data.get('new_password')
    if not old_pw or not new_pw:
        return jsonify({'message': 'Both old_password and new_password are required'}), 400
    if not current_user.check_password(old_pw):
        return jsonify({'message': 'La contraseña actual es incorrecta'}), 401
    if len(new_pw) < 6:
        return jsonify({'message': 'La nueva contraseña debe tener al menos 6 caracteres'}), 400
    current_user.set_password(new_pw)
    db.session.commit()
    return jsonify({'message': 'Password updated'})
@app.route('/api/secretaria/enroll', methods=['POST'])
@token_required
def enroll_student(current_user):
    """Inscribir un estudiante a una materia o a todas las de Humanística."""
    if current_user.role not in ['secretaria', 'director']:
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    student_id = data.get('student_id')
    subject_id = data.get('subject_id')
    level = data.get('level', 'Único')
    area = data.get('area', 'Técnica')
    
    if not student_id or not subject_id:
        return jsonify({'message': 'student_id and subject_id are required'}), 400
    
    student = User.query.filter_by(id=student_id, role='estudiante').first()
    if not student:
        return jsonify({'message': 'Estudiante no encontrado'}), 404

    if subject_id == 'TODAS' and area == 'Humanística':
        subjects_to_enroll = [
            'Matematicas',
            'Lenguaje y Comunicacion',
            'Ciencias Naturales',
            'Ciencias Sociales'
        ]
        enrollments = []
        for s_name in subjects_to_enroll:
            subject = Subject.query.filter_by(name=s_name, area='Humanística').first()
            if not subject:
                subject = Subject(name=s_name, area='Humanística', teacher_id=None)
                db.session.add(subject)
                db.session.flush()
            
            existing_enr = Enrollment.query.filter_by(student_id=student.id, subject_id=subject.id, level=level).first()
            if not existing_enr:
                enr = Enrollment(student_id=student.id, subject_id=subject.id, level=level)
                db.session.add(enr)
                enrollments.append(enr)
        
        db.session.commit()
        return jsonify({
            'message': 'Inscripción múltiple exitosa', 
            'enrollments': [e.to_dict() for e in enrollments],
            'subject_name': 'Todas las materias (Humanística)'
        }), 201

    # Single subject enrollment (fallback to existing logic)
    try:
        subject_id_int = int(subject_id)
        subject = Subject.query.filter_by(id=subject_id_int).first()
    except (ValueError, TypeError):
        # subject_id is actually a name string
        subject = Subject.query.filter_by(name=subject_id, area=area).first()
        if not subject:
            # Create the subject if it doesn't exist yet
            subject = Subject(name=subject_id, area=area, teacher_id=None)
            db.session.add(subject)
            db.session.flush()  # get the ID without committing
    
    if not subject:
        return jsonify({'message': 'Materia no encontrada'}), 404
    
    # Check if already enrolled in this exact subject and level
    existing_enr = Enrollment.query.filter_by(student_id=student.id, subject_id=subject.id, level=level).first()
    if existing_enr:
        return jsonify({'message': 'El estudiante ya está inscrito en este nivel de la materia'}), 400
        
    enrollment = Enrollment(student_id=student.id, subject_id=subject.id, level=level)
    db.session.add(enrollment)
    db.session.commit()
    return jsonify({'message': 'Inscripción exitosa', 'enrollment': enrollment.to_dict()}), 201

@app.route('/api/secretaria/assign_teacher_level', methods=['POST'])
@token_required
def assign_teacher_level(current_user):
    if current_user.role not in ['secretaria', 'director']:
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    teacher_id = data.get('teacher_id')
    subject_name = data.get('subject_name')
    area = data.get('area')
    level = data.get('level')
    
    if not teacher_id or not subject_name or not area or not level:
        return jsonify({'message': 'Missing required fields'}), 400
        
    teacher = User.query.filter_by(id=teacher_id, role='profesor').first()
    if not teacher:
        return jsonify({'message': 'Teacher not found'}), 404
        
    # Clear previous assignments for this teacher
    Subject.query.filter_by(teacher_id=teacher_id).update({"teacher_id": None})

    if subject:
        # Assign teacher to existing subject
        subject.teacher_id = teacher_id
    else:
        # Create new level-specific subject record
        subject = Subject(name=subject_name, area=area, level=level, teacher_id=teacher_id)
        db.session.add(subject)
        
    db.session.commit()
    return jsonify({'message': 'Teacher assigned to level successfully', 'subject': subject.to_dict()})

@app.route('/api/secretaria/enroll/<int:enrollment_id>', methods=['DELETE'])
@token_required
def unenroll_student(current_user, enrollment_id):
    """Eliminar una inscripción."""
    if current_user.role not in ['secretaria', 'director']:
        return jsonify({'message': 'Unauthorized'}), 403
    enrollment = Enrollment.query.get_or_404(enrollment_id)
    db.session.delete(enrollment)
    db.session.commit()
    return jsonify({'message': 'Inscripción eliminada exitosamente'})

@app.route('/api/secretaria/report/enrollments_by_level', methods=['GET'])
@token_required
def report_enrollments_by_level(current_user):
    if current_user.role not in ['director', 'secretaria']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    level = request.args.get('level')
    if not level:
        return jsonify({'message': 'Falta el nivel'}), 400
    
    # Query enrollments for this level
    enrollments = Enrollment.query.filter_by(level=level).all()
    
    results = []
    for enr in enrollments:
        teacher_name = "No asignado"
        subject_name = enr.subject.name if enr.subject else "N/A"
        # Since we use subject name 'Sin especialidad' for EPA, we rename it here too
        if subject_name == 'Sin especialidad':
            subject_name = 'EDUCACION PRIMARIA DE ADULTOS'
            
        if enr.subject and enr.subject.teacher:
            teacher_name = f"{enr.subject.teacher.first_name} {enr.subject.teacher.last_name}"
            
        results.append({
            'id': enr.id,
            'student_id': enr.student_id,
            'student_name': f"{enr.student.first_name} {enr.student.last_name}" if enr.student else "N/A",
            'student_carnet': enr.student.carnet if enr.student else "N/A",
            'area': enr.subject.area if enr.subject else "N/A",
            'subject': subject_name,
            'level': enr.level,
            'teacher': teacher_name
        })
        
    return jsonify(results)
# ─── DOCUMENTS ────────────────────────────────────────────────────────────────
@app.route('/api/secretaria/documents/<int:student_id>', methods=['GET'])
@token_required
def get_student_documents(current_user, student_id):
    if current_user.role not in ['secretaria', 'director']:
        return jsonify({'message': 'Unauthorized'}), 403
    
    docs = StudentDocument.query.filter_by(student_id=student_id).all()
    
    # Auto-initialize default documents if missing
    if not docs:
        default_docs = ["Certificado de Nacimiento", "Cédula de Identidad", "Libreta Escolar"]
        for d in default_docs:
            new_doc = StudentDocument(student_id=student_id, document_name=d, is_submitted=False)
            db.session.add(new_doc)
        db.session.commit()
        docs = StudentDocument.query.filter_by(student_id=student_id).all()
        
    return jsonify([d.to_dict() for d in docs])
@app.route('/api/secretaria/documents', methods=['POST'])
@token_required
def add_document_requirement(current_user):
    if current_user.role not in ['secretaria', 'director']:
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    doc = StudentDocument(
        student_id=data['student_id'],
        document_name=data['document_name'],
        is_submitted=data.get('is_submitted', False)
    )
    db.session.add(doc)
    db.session.commit()
    return jsonify(doc.to_dict()), 201
@app.route('/api/secretaria/documents/<int:doc_id>/toggle', methods=['PUT'])
@token_required
def toggle_document(current_user, doc_id):
    if current_user.role not in ['secretaria', 'director']:
        return jsonify({'message': 'Unauthorized'}), 403
    doc = StudentDocument.query.get_or_404(doc_id)
    doc.is_submitted = not doc.is_submitted
    db.session.commit()
    return jsonify(doc.to_dict())
@app.route('/api/secretaria/documents/<int:doc_id>', methods=['DELETE'])
@token_required
def delete_document(current_user, doc_id):
    if current_user.role not in ['secretaria', 'director']:
        return jsonify({'message': 'Unauthorized'}), 403
    doc = StudentDocument.query.get_or_404(doc_id)
    db.session.delete(doc)
    db.session.commit()
    return jsonify({'message': 'Documento eliminado exitosamente'})
# ─── TEACHER ──────────────────────────────────────────────────────────────────
@app.route('/api/profesor/subjects', methods=['GET'])
@token_required
def teacher_subjects(current_user):
    if current_user.role != 'profesor':
        return jsonify({'message': 'Unauthorized'}), 403
    subjects = Subject.query.filter_by(teacher_id=current_user.id).all()
    return jsonify([s.to_dict() for s in subjects])
@app.route('/api/profesor/students_by_subject/<int:subject_id>', methods=['GET'])
@token_required
def students_by_subject(current_user, subject_id):
    if current_user.role != 'profesor':
        return jsonify({'message': 'Unauthorized'}), 403
    subject = Subject.query.filter_by(id=subject_id, teacher_id=current_user.id).first()
    if not subject:
        return jsonify({'message': 'Subject not found or unauthorized'}), 404
    enrollments = Enrollment.query.filter_by(subject_id=subject.id).all()
    students = []
    for enr in enrollments:
        student_data = enr.student.to_dict()
        student_data['enrollment_id'] = enr.id
        student_data['level'] = enr.level
        grades = Grade.query.filter_by(enrollment_id=enr.id).all()
        student_data['grades'] = [g.to_dict() for g in grades]
        students.append(student_data)
    return jsonify({'subject': subject.name, 'area': subject.area, 'students': students})
@app.route('/api/profesor/grade', methods=['POST'])
@token_required
def assign_grade(current_user):
    if current_user.role != 'profesor':
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    enrollment_id = data.get('enrollment_id')
    dimension = data.get('dimension') # Now represents module name like 'Módulo 1'
    score = data.get('score')
    
    if not enrollment_id or not dimension or score is None:
        return jsonify({'message': 'enrollment_id, dimension and score are required'}), 400
    
    enr = Enrollment.query.filter_by(id=enrollment_id).first()
    if not enr or enr.subject.teacher_id != current_user.id:
        return jsonify({'message': 'Unauthorized to grade this text'}), 403
        
    grade = Grade.query.filter_by(enrollment_id=enrollment_id, dimension=dimension).first()
    if grade:
        grade.score = score
    else:
        grade = Grade(enrollment_id=enrollment_id, dimension=dimension, score=score)
        db.session.add(grade)
    db.session.commit()
    return jsonify({'message': 'Grade assigned correctly', 'grade': grade.to_dict()})
# ─── SUBJECT MATERIALS ────────────────────────────────────────────────────────
@app.route('/api/profesor/materials/<int:subject_id>', methods=['GET'])
@token_required
def get_subject_materials(current_user, subject_id):
    if current_user.role != 'profesor':
        return jsonify({'message': 'Unauthorized'}), 403
    materials = SubjectMaterial.query.filter_by(subject_id=subject_id).all()
    return jsonify([m.to_dict() for m in materials])
@app.route('/api/profesor/materials', methods=['POST'])
@token_required
def add_subject_material(current_user):
    if current_user.role != 'profesor':
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    subject = Subject.query.filter_by(id=data['subject_id'], teacher_id=current_user.id).first()
    if not subject:
        return jsonify({'message': 'Subject not found or not assigned to you'}), 404
    mat = SubjectMaterial(
        subject_id=data['subject_id'],
        teacher_id=current_user.id,
        title=data['title'],
        url=data['url']
    )
    db.session.add(mat)
    db.session.commit()
    return jsonify(mat.to_dict()), 201
@app.route('/api/profesor/materials/<int:mid>', methods=['DELETE'])
@token_required
def delete_subject_material(current_user, mid):
    if current_user.role != 'profesor':
        return jsonify({'message': 'Unauthorized'}), 403
    mat = SubjectMaterial.query.get_or_404(mid)
    if mat.teacher_id != current_user.id:
        return jsonify({'message': 'Unauthorized'}), 403
    db.session.delete(mat)
    db.session.commit()
    return jsonify({'message': 'Material eliminado'})
# ─── STUDENT ──────────────────────────────────────────────────────────────────
@app.route('/api/estudiante/grades', methods=['GET'])
@token_required
def get_student_grades(current_user):
    if current_user.role != 'estudiante':
        return jsonify({'message': 'Unauthorized'}), 403
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    results = []
    for enr in enrollments:
        grades = Grade.query.filter_by(enrollment_id=enr.id).all()
        grades_dict = {g.dimension: g.score for g in grades}
        area = enr.subject.area if enr.subject else 'Humanística'
        level = enr.level or 'Único'
        
        if area == 'Técnica':
            modules = ['Módulo 1', 'Módulo 2', 'Módulo 3', 'Módulo 4', 'Módulo 5']
            module_scores = [grades_dict.get(m) for m in modules]
            filled = [s for s in module_scores if s is not None]
            promedio = round(sum(filled) / len(filled), 1) if filled else None
            estado = 'Aprobado' if (promedio is not None and promedio >= 51) else ('Sin notas' if promedio is None else 'Reprobado')
        else:
            modules = ['Módulo 1', 'Módulo 2']
            module_scores = [grades_dict.get(m) for m in modules]
            filled = [s for s in module_scores if s is not None]
            promedio = round(sum(filled) / len(filled), 1) if filled else None
            estado = 'Aprobado' if (promedio is not None and promedio >= 51) else ('Sin notas' if promedio is None else 'Reprobado')
        
        teacher_name = f"{enr.subject.teacher.first_name} {enr.subject.teacher.last_name}" if enr.subject and enr.subject.teacher else "No asignado"
        results.append({
            'subject': enr.subject.name,
            'subject_id': enr.subject_id,
            'area': area,
            'level': level,
            'teacher_name': teacher_name,
            'modules': modules,
            'module_scores': {m: grades_dict.get(m) for m in modules},
            'promedio': promedio,
            'estado': estado
        })
    return jsonify(results)
@app.route('/api/estudiante/materials/<int:subject_id>', methods=['GET'])
@token_required
def get_student_subject_materials(current_user, subject_id):
    if current_user.role != 'estudiante':
        return jsonify({'message': 'Unauthorized'}), 403
    enr = Enrollment.query.filter_by(student_id=current_user.id, subject_id=subject_id).first()
    if not enr:
        return jsonify({'message': 'Not enrolled in this subject'}), 403
    materials = SubjectMaterial.query.filter_by(subject_id=subject_id).all()
    return jsonify([m.to_dict() for m in materials])
# ─── MESSAGES ────────────────────────────────────────────────────────────────
@app.route('/api/messages', methods=['GET'])
@token_required
def get_messages(current_user):
    received = Communication.query.filter_by(receiver_id=current_user.id).order_by(Communication.timestamp.desc()).all()
    sent_raw = Communication.query.filter_by(sender_id=current_user.id).order_by(Communication.timestamp.desc()).all()
    
    # Agrupar mensajes enviados idénticos (anuncios masivos)
    sent_grouped = {}
    for m in sent_raw:
        # Agrupamos por mensaje y fecha (minutos)
        group_key = f"{m.message}_{m.timestamp.strftime('%Y%m%d%H%M')}"
        if group_key not in sent_grouped:
            sent_grouped[group_key] = {
                'id': m.id,
                'message': m.message,
                'date': m.timestamp.strftime("%Y-%m-%d %H:%M"),
                'receivers': []
            }
        sent_grouped[group_key]['receivers'].append(m.receiver.role)
    
    sent_list = []
    for grp in sent_grouped.values():
        rec_roles = list(set(grp['receivers'])) # evitar duplicados de rol si hay varios
        if len(grp['receivers']) > 1:
            receiver_label = f"Múltiples usuarios ({', '.join(rec_roles)})"
        else:
            # Si solo fue a 1 persona, mostramos que fue a 1 persona de ese rol
            receiver_label = f"1 Usuario ({rec_roles[0]})"
            
        sent_list.append({
            'id': grp['id'],
            'receiver': receiver_label,
            'message': grp['message'],
            'date': grp['date']
        })
    return jsonify({
        'received': [{
            'id': m.id,
            'sender': f"{m.sender.first_name} {m.sender.last_name}",
            'sender_role': m.sender.role,
            'message': m.message,
            'date': m.timestamp.strftime("%Y-%m-%d %H:%M")
        } for m in received],
        'sent': sent_list
    })
@app.route('/api/messages/send', methods=['POST'])
@token_required
def send_message(current_user):
    data = request.get_json()
    new_msg = Communication(
        sender_id=current_user.id,
        receiver_id=data['receiver_id'],
        message=data['message']
    )
    db.session.add(new_msg)
    db.session.commit()
    return jsonify({'message': 'Mensaje enviado', 'id': new_msg.id})
@app.route('/api/announcement', methods=['POST'])
@token_required
def send_announcement(current_user):
    data = request.get_json()
    target_role = data.get('target_role')
    message = data.get('message')
    if not message or not target_role:
        return jsonify({'message': 'message and target_role are required'}), 400
    if current_user.role == 'estudiante':
        return jsonify({'message': 'Estudiantes no pueden enviar anuncios'}), 403
    elif current_user.role in ['profesor', 'secretaria']:
        target_role = 'estudiante'
    if target_role == 'todos':
        targets = User.query.all()
    else:
        targets = User.query.filter_by(role=target_role).all()
    if not targets:
        return jsonify({'message': 'No targets found for this role'}), 404
    count = 0
    for t in targets:
        # No enviarse mensaje a sí mismo en un anuncio grupal
        if t.id == current_user.id:
            continue
        new_msg = Communication(
            sender_id=current_user.id,
            receiver_id=t.id,
            message=message
        )
        db.session.add(new_msg)
        count += 1
    
    db.session.commit()
    return jsonify({'message': f'Anuncio enviado a {count} usuarios', 'count': count}), 201
# ─── RESOURCES ────────────────────────────────────────────────────────────────
@app.route('/api/resources', methods=['GET'])
@token_required
def get_resources(current_user):
    resources = Resource.query.all()
    return jsonify([{'id': r.id, 'title': r.title, 'url': r.url, 'type': r.type} for r in resources])
@app.route('/api/resources', methods=['POST'])
@token_required
def add_resource(current_user):
    if current_user.role != 'director':
        return jsonify({'message': 'Unauthorized'}), 403
    data = request.get_json()
    r = Resource(title=data['title'], url=data['url'], type=data.get('type', 'article'), created_by=current_user.id)
    db.session.add(r)
    db.session.commit()
    return jsonify({'id': r.id, 'title': r.title, 'url': r.url, 'type': r.type}), 201
@app.route('/api/resources/<int:rid>', methods=['DELETE'])
@token_required
def delete_resource(current_user, rid):
    if current_user.role != 'director':
        return jsonify({'message': 'Unauthorized'}), 403
    r = Resource.query.get_or_404(rid)
    db.session.delete(r)
    db.session.commit()
    return jsonify({'message': 'Recurso eliminado'})
@app.route('/api/debug/db', methods=['GET'])
def debug_db():
    import traceback
    try:
        data = {
            "users": User.query.count(),
            "subjects": Subject.query.count(),
            "enrollments": Enrollment.query.count(),
            "db_url_end": str(db.engine.url).split('@')[-1] if '@' in str(db.engine.url) else "local"
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route('/api/debug/me', methods=['GET'])
@token_required
def debug_me(current_user):
    """Returns the role and info of the current token's user – for debugging auth issues."""
    return jsonify({
        'id': current_user.id,
        'username': current_user.username,
        'role': current_user.role,
        'first_name': current_user.first_name,
        'last_name': current_user.last_name,
    })

@app.route('/api/migrate_usernames', methods=['GET'])
def migrate_usernames():
    try:
        users = User.query.all()
        count = 0
        for u in users:
            new_username = f"{u.first_name}{u.last_name}@educonnect.com".replace(" ", "").lower()
            if u.username != new_username:
                u.username = new_username
                count += 1
        db.session.commit()
        return jsonify({"message": f"Migrated {count} users to new email usernames."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/director/stats/performance', methods=['GET'])
@token_required
def performance_stats(current_user):
    if current_user.role != 'director':
        return jsonify({'message': 'Unauthorized'}), 403
    
    levels = [
        "NIVEL BASICO", "NIVEL AUXILIAR", "NIVEL MEDIO I", "NIVEL MEDIO II",
        "CICLO DE APRENDIZAJES APLICADOS", "CICLO DE APRENDIZAJES COMPLEMENTARIOS", "CICLO DE APRENDIZAJES ESPECIALIZADOS"
    ]
    performance = {}
    
    for lvl in levels:
        enrollments = Enrollment.query.filter_by(level=lvl).all()
        if not enrollments:
            performance[lvl] = {"avg": 0, "pass": 0, "fail": 0, "total": 0}
            continue
            
        total_score = 0
        pass_count = 0
        fail_count = 0
        valid_students = 0
        
        for enr in enrollments:
            grades = Grade.query.filter_by(enrollment_id=enr.id).all()
            if not grades:
                continue
                
            student_avg = sum(g.score for g in grades) / len(grades)
            total_score += student_avg
            if student_avg >= 61:
                pass_count += 1
            else:
                fail_count += 1
            valid_students += 1
            
        performance[lvl] = {
            "avg": round(total_score / valid_students, 1) if valid_students > 0 else 0,
            "pass": pass_count,
            "fail": fail_count,
            "total": valid_students
        }
        
    return jsonify(performance)

@app.route('/api/admin/reset_password', methods=['POST'])
@token_required
def admin_reset_password(current_user):
    if current_user.role not in ['director', 'secretaria']:
        return jsonify({'message': 'Unauthorized'}), 403
        
    data = request.get_json()
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'message': 'user_id is required'}), 400
        
    user = User.query.get_or_404(user_id)
    user.set_password(user.carnet)
    db.session.commit()
    
    return jsonify({'message': f'Contraseña de {user.first_name} restablecida a su carnet correctamente.'})

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@token_required
def admin_delete_user(current_user, user_id):
    if current_user.role not in ['director', 'secretaria']:
        return jsonify({'message': 'Unauthorized'}), 403
        
    if current_user.id == user_id:
        return jsonify({'message': 'No puedes eliminarte a ti mismo'}), 400
        
    user = User.query.get_or_404(user_id)
    
    # Optional: Check if deleting an admin
    if user.role == 'director' and current_user.role != 'director':
        return jsonify({'message': 'Solo un Director puede eliminar a otro Director'}), 403

    db.session.delete(user)
    db.session.commit()
    return jsonify({'message': f'Usuario {user.first_name} {user.last_name} eliminado correctamente.'})
