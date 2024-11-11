from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.contrib.github import make_github_blueprint, github
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from bson import ObjectId
import os
import dropbox  
from datetime import datetime

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# MongoDB settings
USERS_MONGO_URI = os.getenv('USERS_MONGO_URI')
APPLICATIONS_MONGO_URL = os.getenv('APPLICATIONS_MONGO_URL')
client = MongoClient(USERS_MONGO_URI)
db = client.get_database()
users_collection = db['users']

client_apps = MongoClient(APPLICATIONS_MONGO_URL)
db_apps = client_apps['applicationsdb']
uploads_collection = db_apps['uploads']

# Login management
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

CORS(app)

# Dropbox settings
DROPBOX_ACCESS_TOKEN = os.getenv('DROPBOX_TOKEN') 
dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)

# User model
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email

    @staticmethod
    def get_by_id(user_id):
        user = users_collection.find_one({'_id': ObjectId(user_id)})
        if user:
            return User(str(user['_id']), user['username'], user['email'])
        return None

# User login management
@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)

@app.route('/')
def index():
    return render_template('index.html', user=current_user)

@app.route('/test')
def test():
    return render_template('test.html', user=current_user)

@app.route('/json/<filename>') 
def serve_json(filename):
    return send_from_directory('json', filename)

@app.route('/images/<filename>') 
def serve_images(filename):
    return send_from_directory('images', filename)

@app.route('/js/<filename>') 
def serve_js(filename):
    return send_from_directory('js', filename)

@app.route('/css/<filename>') 
def serve_css(filename):
    return send_from_directory('css', filename)

@app.route('/<filename>') 
def serve_html(filename):
    return render_template(f"{filename}.html", user=current_user)

# Google Login
@app.route('/google/login')
def google_login():
    if not google.authorized:
        return redirect(url_for('google.login'))

    try:
        google_info = google.get('/plus/v1/people/me')
        if google_info.status != 200:
            flash('Google login failed')
            return redirect(url_for('home'))
        
        google_data = google_info.json()
        username = google_data['displayName']
        email = google_data['emails'][0]['value']

        user = users_collection.find_one({'email': email})
        if not user:
            users_collection.insert_one({
                'username': username,
                'email': email,
                'password': '',
                'google': True,
            })
            user = users_collection.find_one({'email': email})  # Reload user data

        user_obj = User(str(user['_id']), user['username'], user['email'])
        login_user(user_obj)
        return redirect(url_for('dashboard'))

    except Exception as e:
        flash(f"Error occurred during Google login: {e}")
        return redirect(url_for('home'))

# GitHub Login
@app.route('/github/authorized')
def github_login():
    if not github.authorized:
        return redirect(url_for('github.login'))

    try:
        github_info = github.get('/user')
        if github_info.status != 200:
            flash('GitHub login failed')
            return redirect(url_for('home'))

        github_data = github_info.json()
        username = github_data['login']
        email = github_data['email']

        user = users_collection.find_one({'email': email})
        if not user:
            users_collection.insert_one({
                'username': username,
                'email': email,
                'password': '',
                'github': True,
            })
            user = users_collection.find_one({'email': email})  # Reload user data

        user_obj = User(str(user['_id']), user['username'], user['email'])
        login_user(user_obj)
        return redirect(url_for('dashboard'))

    except Exception as e:
        flash(f"Error occurred during GitHub login: {e}")
        return redirect(url_for('home'))

# Dashboard
@app.route('/dashboard')
@login_required
def dashboard():
    user_uploads_cursor = uploads_collection.find({'uploaded_by': current_user.username})
    user_uploads = list(user_uploads_cursor)

    for upload in user_uploads:
        if 'download_link' not in upload or not upload['download_link']:
            dropbox_path = upload['file_path']
            try:
                shared_link_metadata = dbx.sharing_get_shared_link_metadata(dropbox_path)
                upload['download_link'] = shared_link_metadata.url.replace("?dl=0", "?dl=1")
                uploads_collection.update_one(
                    {'_id': upload['_id']},
                    {'$set': {'download_link': upload['download_link']}}
                )
            except dropbox.exceptions.ApiError as e:
                if isinstance(e.error, dropbox.sharing.SharedLinkError.SharedLinkLookupError):
                    try:
                        shared_link_metadata = dbx.sharing_create_shared_link_with_settings(dropbox_path)
                        upload['download_link'] = shared_link_metadata.url.replace("?dl=0", "?dl=1")
                        uploads_collection.update_one(
                            {'_id': upload['_id']},
                            {'$set': {'download_link': upload['download_link']}}
                        )
                    except dropbox.exceptions.ApiError:
                        upload['download_link'] = None
                else:
                    upload['download_link'] = None

    return render_template('dashboard.html', user=current_user, uploads=user_uploads)

# Logout
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('index'))

# Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        email = request.form['email']

        if password != confirm_password:
            flash('Passwords do not match.')
            return redirect(url_for('register'))

        existing_user = users_collection.find_one({'username': username})
        if existing_user:
            flash('Username already exists.')
            return redirect(url_for('register'))

        hashed_password = generate_password_hash(password)
        users_collection.insert_one({
            'username': username,
            'password': hashed_password,
            'email': email,
            'google': False,
            'github': False
        })

        flash('Registration successful. You can now log in.')
        return redirect(url_for('login'))

    return render_template('register.html')

# Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = users_collection.find_one({'username': username})

        if user:
            if check_password_hash(user['password'], password):
                user_obj = User(str(user['_id']), user['username'], user['email'])
                login_user(user_obj)
                return redirect(url_for('dashboard'))
            else:
                flash('Invalid username or password.')
        else:
            flash('Invalid username or password.')

        return redirect(url_for('login'))

    return render_template('login.html')

# Profile
@app.route('/profile')
@login_required
def profile():
    user = current_user
    return render_template('profile.html', user=user)

# File upload
@app.route('/upload-file', methods=['POST'])
@login_required
def upload_file():
    version = request.form['version']
    app_name = request.form['app_name']
    app_tags = request.form['app_tags']
    app_type = request.form['app_type']
    uploader_name = current_user.username

    if 'file' not in request.files:
        flash("No file part")
        return redirect(url_for('upload_file'))  # Change 'upload' to 'upload_file'

    file = request.files['file']
    if file.filename == '':
        flash("No selected file")
        return redirect(url_for('upload_file'))  # Change 'upload' to 'upload_file'

    file_extension = file.filename.split('.')[-1].lower()
    if file_extension not in ['exe', 'ipa', 'apk']:
        flash("Only EXE, IPA, and APK files are allowed.")
        return redirect(url_for('upload_file'))  # Change 'upload' to 'upload_file'

    uid = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{uploader_name}_{uid}_{file.filename}"

    folder = 'exe_files' if file_extension == 'exe' else 'ipa_files' if file_extension == 'ipa' else 'apk_files'
    dropbox_path = f'/{folder}/{filename}'

    try:
        dbx.files_upload(file.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)
    except Exception as e:
        flash(f"Error uploading file: {e}")
        return redirect(url_for('upload_file'))  # Change 'upload' to 'upload_file'

    try:
        shared_link_metadata = dbx.sharing_create_shared_link_with_settings(dropbox_path)
        download_link = shared_link_metadata.url.replace("?dl=0", "?dl=1")
    except dropbox.exceptions.ApiError as e:
        download_link = None

    uploads_collection.insert_one({
        'app_name': app_name,
        'app_type': app_type,
        'version': version,
        'tags': app_tags,
        'file_path': dropbox_path,
        'download_link': download_link,
        'upload_time': datetime.utcnow(),
        'uploaded_by': uploader_name
    })

    flash('File uploaded successfully!')
    return redirect(url_for('dashboard'))  # Redirect to dashboard after successful upload

if __name__ == '__main__':
    app.run(debug=True,port=10000,host='0.0.0.0')
