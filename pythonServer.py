from flask import Flask, request, jsonify, render_template, send_from_directory, send_file, Response
from flask_swagger_ui import get_swaggerui_blueprint
import sqlite3
import jwt
import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this-in-production'

# Video upload configuration
UPLOAD_FOLDER = 'uploads/videos'
ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'wmv', 'flv', 'webm'}
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# Create upload folder if it doesn't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database connection helper
def get_db_connection():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Token required decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        try:
            if token.startswith('Bearer '):
                token = token.split(' ')[1]
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user_id = data['user_id']
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        
        return f(current_user_id, *args, **kwargs)
    
    return decorated

# Swagger UI configuration
SWAGGER_URL = '/swagger'
API_URL = '/static/swagger.json'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Workstation Tracking API"
    }
)

app.register_blueprint(swaggerui_blueprint, url_prefix=SWAGGER_URL)

CORS(app, resources={
    r"/api/*": {
        "origins": '*',
        "methods": ["GET", "POST", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

# ==================== USER APIs ====================
@app.route("/")
def home():
    return render_template("dashboard.html")


@app.route("/1")
def home1():
    return render_template("d1.html")

@app.route('/api/user/create', methods=['POST'])
def create_user():
    """Create a new user"""
    data = request.get_json()
    
    if not data or not data.get('name') or not data.get('password') or not data.get('role'):
        return jsonify({'message': 'Missing required fields: name, password, role'}), 400
    
    if data['role'] not in ['admin', 'guest']:
        return jsonify({'message': 'Role must be either admin or guest'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        hashed_password = generate_password_hash(data['password'])
        
        cursor.execute("""
            INSERT INTO user_table (name, role, is_active)
            VALUES (?, ?, ?)
        """, (data['name'], data['role'], data.get('is_active', 'y')))
        
        user_id = cursor.lastrowid
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'User created successfully',
            'user_id': user_id
        }), 201
        
    except Exception as e:
        return jsonify({'message': f'Error creating user: {str(e)}'}), 500

@app.route('/api/user/login', methods=['POST'])
def login_user():
    """Login user and get JWT token"""
    data = request.get_json()
    
    if not data or not data.get('name') or not data.get('password'):
        return jsonify({'message': 'Missing name or password'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM user_table WHERE name = ? AND is_active = 'y'", (data['name'],))
        user = cursor.fetchone()
        conn.close()
        
        if not user:
            return jsonify({'message': 'Invalid credentials'}), 401
        
        token = jwt.encode({
            'user_id': user['id'],
            'name': user['name'],
            'role': user['role'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=24)
        }, app.config['SECRET_KEY'], algorithm="HS256")
        
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': {
                'id': user['id'],
                'name': user['name'],
                'role': user['role']
            }
        }), 200
        
    except Exception as e:
        return jsonify({'message': f'Error during login: {str(e)}'}), 500

# ==================== WORKSTATION APIs ====================

@app.route('/api/workstation/create', methods=['POST'])
@token_required
def create_workstation(current_user_id):
    """Create a new workstation"""
    data = request.get_json()
    
    required_fields = ['workstation_name', 'system_mac_id', 'camera_url']
    if not all(field in data for field in required_fields):
        return jsonify({'message': f'Missing required fields: {", ".join(required_fields)}'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO workstation (
                workstation_name, system_mac_id, camera_url, camera_quality,
                pre_video_time, process_video_time, fps, is_active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['workstation_name'],
            data['system_mac_id'],
            data['camera_url'],
            data.get('camera_quality', 'HD'),
            data.get('pre_video_time', 30),
            data.get('process_video_time', 60),
            data.get('fps', 30),
            data.get('is_active', 'y')
        ))
        
        workstation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Workstation created successfully',
            'workstation_id': workstation_id
        }), 201
        
    except Exception as e:
        return jsonify({'message': f'Error creating workstation: {str(e)}'}), 500

@app.route('/api/workstation/list', methods=['GET'])
@token_required
def list_workstations(current_user_id):
    """Get paginated list of workstations with filters"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        offset = (page - 1) * per_page
        
        is_active = request.args.get('is_active', None)
        workstation_name = request.args.get('workstation_name', None)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM workstation WHERE 1=1"
        params = []
        
        if is_active:
            query += " AND is_active = ?"
            params.append(is_active)
        
        if workstation_name:
            query += " AND workstation_name LIKE ?"
            params.append(f'%{workstation_name}%')
        
        count_query = query.replace("SELECT *", "SELECT COUNT(*)")
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        
        query += " ORDER BY doa DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        
        cursor.execute(query, params)
        workstations = cursor.fetchall()
        conn.close()
        
        return jsonify({
            'data': [dict(ws) for ws in workstations],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': (total_count + per_page - 1) // per_page
            }
        }), 200
        
    except Exception as e:
        return jsonify({'message': f'Error fetching workstations: {str(e)}'}), 500

# ==================== PACKAGING (TRACKING) APIs ====================

@app.route('/api/packaging/create', methods=['POST'])
def create_packaging():
    """Create a new packaging record"""
    data = request.get_json()
    
    if not data or not data.get('bar_code_1'):
        return jsonify({'message': 'Missing required field: bar_code_1'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO tracking_table (
                bar_code_1, start_time, bar_code_2, end_time, video_path, is_active
            ) VALUES (?, ?, ?, ?, ?, ?)
        """, (
            data['bar_code_1'],
            data.get('start_time', datetime.datetime.now().isoformat()),
            data.get('bar_code_2'),
            data.get('end_time'),
            data.get('video_path'),
            data.get('is_active', 'y')
        ))
        
        packaging_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Packaging record created successfully',
            'packaging_id': packaging_id
        }), 201
        
    except Exception as e:
        return jsonify({'message': f'Error creating packaging record: {str(e)}'}), 500

@app.route('/api/packaging/update/<int:packaging_id>', methods=['PUT'])
def update_packaging(packaging_id):
    """Update an existing packaging record"""
    data = request.get_json()
    
    if not data:
        return jsonify({'message': 'No data provided'}), 400
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        update_fields = []
        params = []
        
        allowed_fields = ['bar_code_1', 'start_time', 'bar_code_2', 'end_time', 'video_path', 'is_active']
        
        for field in allowed_fields:
            if field in data:
                update_fields.append(f"{field} = ?")
                params.append(data[field])
        
        if not update_fields:
            return jsonify({'message': 'No valid fields to update'}), 400
        
        params.append(packaging_id)
        
        query = f"UPDATE tracking_table SET {', '.join(update_fields)} WHERE id = ?"
        cursor.execute(query, params)
        
        if cursor.rowcount == 0:
            conn.close()
            return jsonify({'message': 'Packaging record not found'}), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Packaging record updated successfully'}), 200
        
    except Exception as e:
        return jsonify({'message': f'Error updating packaging record: {str(e)}'}), 500

@app.route('/api/packaging/list', methods=['GET'])
@token_required
def list_packaging(current_user_id):
    """Get paginated list of packaging records with filters"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        offset = (page - 1) * per_page
        
        is_active = request.args.get('is_active', None)
        bar_code_1 = request.args.get('bar_code_1', None)
        bar_code_2 = request.args.get('bar_code_2', None)
        start_date = request.args.get('start_date', None)
        end_date = request.args.get('end_date', None)
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        query = "SELECT * FROM tracking_table WHERE 1=1"
        params = []
        
        if is_active:
            query += " AND is_active = ?"
            params.append(is_active)
        
        if bar_code_1:
            query += " AND bar_code_1 LIKE ?"
            params.append(f'%{bar_code_1}%')
        
        if bar_code_2:
            query += " AND bar_code_2 LIKE ?"
            params.append(f'%{bar_code_2}%')
        
        if start_date:
            query += " AND start_time >= ?"
            params.append(start_date)
        
        if end_date:
            query += " AND end_time <= ?"
            params.append(end_date)
        
        count_query = query.replace("SELECT *", "SELECT COUNT(*)")
        cursor.execute(count_query, params)
        total_count = cursor.fetchone()[0]
        
        query += " ORDER BY doa DESC LIMIT ? OFFSET ?"
        params.extend([per_page, offset])
        
        cursor.execute(query, params)
        packaging_records = cursor.fetchall()
        conn.close()
        
        return jsonify({
            'data': [dict(record) for record in packaging_records],
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total_count,
                'pages': (total_count + per_page - 1) // per_page
            }
        }), 200
        
    except Exception as e:
        return jsonify({'message': f'Error fetching packaging records: {str(e)}'}), 500

@app.route('/api/packaging/upload-video/<int:packaging_id>', methods=['POST'])
def upload_video(packaging_id):
    """Upload video for an existing packaging record"""
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if record exists
        cursor.execute("SELECT * FROM tracking_table WHERE id = ?", (packaging_id,))
        existing_record = cursor.fetchone()
        
        if not existing_record:
            conn.close()
            return jsonify({'message': 'Packaging record not found'}), 404
        
        # Check if video file is present
        if 'video' not in request.files:
            return jsonify({'message': 'No video file provided'}), 400
        
        video_file = request.files['video']
        
        # Check if file is selected
        if video_file.filename == '':
            return jsonify({'message': 'No video file selected'}), 400
        
        # Validate file type
        if not allowed_file(video_file.filename):
            return jsonify({
                'message': f'Invalid file type. Allowed types: {", ".join(ALLOWED_EXTENSIONS)}'
            }), 400
        
        # Generate secure filename with timestamp
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        original_filename = secure_filename(video_file.filename)
        filename = f"packaging_{packaging_id}_{timestamp}_{original_filename}"
        
        # Ensure upload folder exists
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        # Save the video file
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        video_file.save(video_path)
        
        print(f"[UPLOAD] Video saved to: {video_path}")
        print(f"[UPLOAD] File exists: {os.path.exists(video_path)}")
        
        # Delete old video if exists
        if existing_record['video_path']:
            old_video_path = existing_record['video_path']
            print(f"[UPLOAD] Attempting to delete old video: {old_video_path}")
            if os.path.exists(old_video_path):
                try:
                    os.remove(old_video_path)
                    print(f"[UPLOAD] Old video deleted")
                except Exception as e:
                    print(f"[UPLOAD] Failed to delete old video: {str(e)}")
                    pass  # Continue even if deletion fails
        
        # Update video path in database - store relative path
        cursor.execute("""
            UPDATE tracking_table 
            SET video_path = ? 
            WHERE id = ?
        """, (video_path, packaging_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'message': 'Video uploaded successfully',
            'video_path': video_path,
            'filename': filename
        }), 200
        
    except Exception as e:
        print(f"[UPLOAD ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': f'Error uploading video: {str(e)}'}), 500

# ==================== VIDEO SERVING ENDPOINTS ====================

@app.route('/api/video/<int:packaging_id>')
def stream_video(packaging_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT video_path FROM tracking_table WHERE id = ?", (packaging_id,))
        record = cursor.fetchone()
        conn.close()

        if not record or not record['video_path']:
            return jsonify({'message': 'Video not found'}), 404

        video_path = os.path.normpath(record['video_path'])

        if not os.path.exists(video_path):
            return jsonify({'message': 'Video file missing'}), 404

        file_size = os.path.getsize(video_path)
        range_header = request.headers.get('Range')

        def generate(start, length):
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = length
                chunk_size = 8192

                while remaining > 0:
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        # No range → send full file
        if not range_header:
            return Response(
                generate(0, file_size),
                200,
                mimetype="video/mp4",
                headers={
                    "Content-Length": str(file_size),
                    "Accept-Ranges": "bytes"
                }
            )

        # Parse range
        byte1, byte2 = 0, None
        match = range_header.replace("bytes=", "").split("-")

        if match[0]:
            byte1 = int(match[0])
        if match[1]:
            byte2 = int(match[1])

        length = file_size - byte1 if byte2 is None else byte2 - byte1 + 1

        return Response(
            generate(byte1, length),
            206,
            mimetype="video/mp4",
            headers={
                "Content-Range": f"bytes {byte1}-{byte1+length-1}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(length)
            }
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'message': str(e)}), 500

@app.route('/api/packaging/download-video/<int:packaging_id>', methods=['GET'])
def download_video(packaging_id):
    """Download video file for a packaging record"""
    try:
        # Get token from header or query parameter
        token = request.headers.get('Authorization')
        token_param = request.args.get('token')
        
        # If no token in header, try query parameter
        if not token and token_param:
            token = f'Bearer {token_param}'
        
        if token:
            try:
                if token.startswith('Bearer '):
                    token = token.split(' ')[1]
                jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            except:
                pass  # Allow download without authentication for now
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT video_path FROM tracking_table WHERE id = ?", (packaging_id,))
        record = cursor.fetchone()
        conn.close()
        
        if not record:
            return jsonify({'message': 'Packaging record not found'}), 404
        
        if not record['video_path']:
            return jsonify({'message': 'No video associated with this packaging record'}), 404
        
        video_path = record['video_path']
        print(f"[DOWNLOAD] Requested path: {video_path}")
        
        # Try to find the file - handle both absolute and relative paths
        if not os.path.exists(video_path):
            # If it's a relative path, try from current directory
            if not os.path.isabs(video_path):
                video_path = os.path.join(os.getcwd(), video_path)
                print(f"[DOWNLOAD] Trying absolute path: {video_path}")
        
        if not os.path.exists(video_path):
            print(f"[DOWNLOAD] File not found: {video_path}")
            return jsonify({'message': f'Video file not found: {video_path}'}), 404
        
        directory = os.path.dirname(os.path.abspath(video_path))
        filename = os.path.basename(video_path)
        
        print(f"[DOWNLOAD] Serving from directory: {directory}, filename: {filename}")
        return send_from_directory(directory, filename, as_attachment=True)
        
    except Exception as e:
        print(f"[DOWNLOAD ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'message': f'Error downloading video: {str(e)}'}), 500

@app.route('/api/packaging/delete-video/<int:packaging_id>', methods=['DELETE'])
@token_required
def delete_video(current_user_id, packaging_id):
    """Delete video file for a packaging record"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT video_path FROM tracking_table WHERE id = ?", (packaging_id,))
        record = cursor.fetchone()
        
        if not record:
            conn.close()
            return jsonify({'message': 'Packaging record not found'}), 404
        
        if not record['video_path']:
            conn.close()
            return jsonify({'message': 'No video associated with this packaging record'}), 404
        
        video_path = record['video_path']
        
        # Delete file from filesystem
        if os.path.exists(video_path):
            os.remove(video_path)
        
        # Update database to remove video path
        cursor.execute("""
            UPDATE tracking_table 
            SET video_path = NULL 
            WHERE id = ?
        """, (packaging_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Video deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'message': f'Error deleting video: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'message': 'API is running'}), 200

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=27189)