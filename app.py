from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify, send_from_directory
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from authlib.integrations.flask_client import OAuth
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from bson import ObjectId
import os
import dropbox  
from datetime import datetime

# Load environment variables from .env file
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

# Initialize OAuth
oauth = OAuth(app)

# Google OAuth configuration
google = oauth.register(
    name='google',
    client_id=os.getenv('GOOGLE_CLIENT_ID'),
    client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
    authorize_url='https://accounts.google.com/o/oauth2/auth',
    authorize_params=None,
    access_token_url='https://oauth2.googleapis.com/token',
    access_token_params=None,
    refresh_token_url=None,
    client_kwargs={'scope': 'openid profile email'},
)

# GitHub OAuth configuration
github = oauth.register(
    name='github',
    client_id=os.getenv('GITHUB_CLIENT_ID'),
    client_secret=os.getenv('GITHUB_CLIENT_SECRET'),
    authorize_url='https://github.com/login/oauth/authorize',
    authorize_params=None,
    access_token_url='https://github.com/login/oauth/access_token',
    access_token_params=None,
    refresh_token_url=None,
    client_kwargs={'scope': 'user:email'},
)

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

# Google Login route
@app.route('/google/login')
def google_login():
    # Redirect to Google OAuth if the user is not authorized
    if not google.authorized:
        return redirect(google.authorize_url(scope='openid profile email'))

    try:
        # Attempt to fetch the user info from Google
        google_info = google.get('https://www.googleapis.com/oauth2/v1/userinfo')

        if google_info.status != 200:
            flash('Google login failed')
            return redirect(url_for('home'))
        
        google_data = google_info.json()
        username = google_data['name']
        email = google_data['email']

        # Find or create user in MongoDB
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
        return redirect(url_for('dashboard'))


# GitHub Login route
@app.route('/github/authorized')
def github_login():
    # Redirect to GitHub OAuth if the user is not authorized
    if not github.authorized:
        return redirect(github.authorize_url(scope='user:email'))

    try:
        # Check if we successfully authorized the access token
        github_info = github.get('/user')

        if github_info.status != 200:
            flash('GitHub login failed')
            return redirect(url_for('home'))

        github_data = github_info.json()
        username = github_data['login']
        email = github_data['email']

        # Find or create user in MongoDB
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
        return redirect(url_for('dashboard'))


# Dashboard route
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

# Logout route
@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('index'))

# Register route
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

# Login route
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

# Profile route
@app.route('/profile')
@login_required
def profile():
    user = current_user
    return render_template('profile.html', user=user)

# File upload route
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
        return redirect(url_for('upload_file'))

    file = request.files['file']
    if file.filename == '':
        flash("No selected file")
        return redirect(url_for('upload_file'))

    # Upload the file to Dropbox
    try:
        file_path = f'/uploads/{app_name}/{version}/{file.filename}'
        dbx.files_upload(file.read(), file_path)

        # Store file metadata in MongoDB
        uploads_collection.insert_one({
            'file_name': file.filename,
            'file_path': file_path,
            'uploaded_by': uploader_name,
            'upload_time': datetime.now(),
            'version': version,
            'app_name': app_name,
            'app_tags': app_tags,
            'app_type': app_type,
        })
        flash("File uploaded successfully.")
        return redirect(url_for('dashboard'))

    except Exception as e:
        flash(f"An error occurred while uploading the file: {str(e)}")
        return redirect(url_for('upload_file'))

if __name__ == '__main__':
    app.run(debug=True, port=10000, host='0.0.0.0')
