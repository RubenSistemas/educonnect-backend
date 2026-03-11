from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
from models import db, create_default_accounts

load_dotenv()

app = Flask(__name__)
# Permitir CORS para todos los orígenes en las rutas /api/
CORS(app, resources={r"/api/*": {"origins": "*"}})

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'super-secret-key-educonnect-ruben')

# Configuración de Base de Datos
database_url = os.environ.get('DATABASE_URL')
if database_url and database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
elif not database_url:
    basedir = os.path.abspath(os.path.dirname(__file__))
    database_url = 'sqlite:///' + os.path.join(basedir, 'educonnect.db')

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

# Health Check (Fundamental para Render)
@app.route('/health')
@app.route('/api/health')
def health_check():
    return jsonify({"status": "healthy", "database": "connected"}), 200

# Importar rutas al final para evitar circularidad
import routes 

# Inicialización de DB
with app.app_context():
    try:
        db.create_all()
        # ── MIGRACIONES SEGURAS ──
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                # 1. Columna 'level' en enrollments
                if 'postgresql' in str(db.engine.url):
                    conn.execute(text("ALTER TABLE enrollments ADD COLUMN IF NOT EXISTS level VARCHAR(100) DEFAULT 'Único'"))
                    conn.execute(text("ALTER TABLE subjects ADD COLUMN IF NOT EXISTS area VARCHAR(100)"))
                else:
                    # SQLite: area en subjects
                    try: conn.execute(text("ALTER TABLE subjects ADD COLUMN area VARCHAR(100) DEFAULT 'Humanística'"))
                    except Exception: pass
                    # SQLite: level en enrollments
                    try: conn.execute(text("ALTER TABLE enrollments ADD COLUMN level VARCHAR(100) DEFAULT 'Único'"))
                    except Exception: pass
                conn.commit()
            print("✅ Migraciones de columnas ejecutadas.")
        except Exception as me:
            print(f"⚠️ Migración omitida o ya existente: {me}")

        create_default_accounts()
        print("✅ Backend inicializado correctamente.")
    except Exception as e:
        print(f"⚠️ Error durante la inicialización: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
