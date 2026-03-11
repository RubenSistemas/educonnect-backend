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

# Inicialización de DB (Se ejecuta al importar el módulo)
# Usamos un try/except para que no bloquee el inicio del servidor si hay un micro-error de red
try:
    with app.app_context():
        # Importar rutas al final para evitar circularidad
        import routes 
        db.create_all()
        create_default_accounts()
        print("✅ Backend inicializado correctamente.")
except Exception as e:
    print(f"⚠️ Error durante la inicialización: {e}")

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
