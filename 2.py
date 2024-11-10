import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_dance.contrib.google import make_google_blueprint, google
from flask_dance.contrib.github import make_github_blueprint, github
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from bson import ObjectId

# 載入 .env 檔案
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')
app.config['SESSION_COOKIE_NAME'] = 'my_session_cookie'

# 設定 LoginManager
login_manager = LoginManager()
login_manager.init_app(app)

# 設定 MongoDB 連接
MONGO_URI = os.getenv('MONGO_URI')
client = MongoClient(MONGO_URI)
db = client.get_database()
users_collection = db['users']

# 設定 Google OAuth
google_bp = make_google_blueprint(client_id=os.getenv('GOOGLE_CLIENT_ID'),
                                  client_secret=os.getenv('GOOGLE_CLIENT_SECRET'),
                                  redirect_to='google_login')
app.register_blueprint(google_bp, url_prefix='/google')

# 設定 GitHub OAuth
github_bp = make_github_blueprint(
    client_id=os.getenv('GITHUB_CLIENT_ID'),
    client_secret=os.getenv('GITHUB_CLIENT_SECRET'),
    redirect_to='github_login'  # GitHub 回調 URL 必須與設定一致
)
app.register_blueprint(github_bp, url_prefix='/github')

# 用戶模型
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

# 用戶登入登出管理
@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(user_id)

@app.route('/')
def home():
    return render_template('home.html')

# Google 登入處理
@app.route('/google/login')
def google_login():
    if not google.authorized:
        return redirect(url_for('google.login'))
    
    google_info = google.get('/plus/v1/people/me')
    if google_info.status != 200:
        flash('Google login failed')
        return redirect(url_for('home'))
    
    google_data = google_info.json()
    username = google_data['displayName']
    email = google_data['emails'][0]['value']
    
    # 檢查該用戶是否已註冊
    user = users_collection.find_one({'email': email})
    if not user:
        # 若未註冊則將用戶資料存入 MongoDB
        users_collection.insert_one({
            'username': username,
            'email': email,
            'password': '',  # Google 登入不需要密碼
            'google': True,
        })
    
    # 創建用戶實例並登入
    user = User(str(user['_id']), username, email)
    login_user(user)
    return redirect(url_for('dashboard'))

# GitHub 登入處理
@app.route('/github/authorized')
def github_login():
    if not github.authorized:
        return redirect(url_for('github.login'))
    
    github_info = github.get('/user')
    if github_info.status != 200:
        flash('GitHub login failed')
        return redirect(url_for('home'))
    
    github_data = github_info.json()
    username = github_data['login']
    email = github_data['email']
    
    # 檢查該用戶是否已註冊
    user = users_collection.find_one({'email': email})
    if not user:
        # 若未註冊則將用戶資料存入 MongoDB
        users_collection.insert_one({
            'username': username,
            'email': email,
            'password': '',  # GitHub 登入不需要密碼
            'github': True,
        })
        user = users_collection.find_one({'email': email})  # 重新讀取用戶資料
    
    # 創建用戶實例並登入
    user_obj = User(str(user['_id']), user['username'], user['email'])
    login_user(user_obj)
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
@login_required
def dashboard():
    return f'Hello {current_user.username}, welcome to your dashboard!'

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('home'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        email = request.form['email']
        
        # 密碼檢查
        if password != confirm_password:
            flash('Passwords do not match.')
            return redirect(url_for('register'))

        # 檢查用戶名是否已存在
        existing_user = users_collection.find_one({'username': username})
        if existing_user:
            flash('Username already exists.')
            return redirect(url_for('register'))

        # 密碼加密
        hashed_password = generate_password_hash(password)
        
        # 插入用戶資料
        users_collection.insert_one({
            'username': username,
            'password': hashed_password,
            'email': email,
            'google': False,
            'github': False
        })
        
        flash('Registration successful. You can now log in.')
        return redirect(url_for('home'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = users_collection.find_one({'username': username})
        
        if user and check_password_hash(user['password'], password):
            user_obj = User(str(user['_id']), user['username'], user['email'])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password.')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/profile')
@login_required
def profile():
    if 'user_id' not in session:
        return redirect(url_for('home'))  # 未登入則跳轉到登入頁面
    
    # 獲取當前用戶資料
    user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
    
    return render_template('profile.html', user=user)

@app.route('/change_password', methods=['GET', 'POST'])
def change_password():
    if 'user_id' not in session:
        return redirect(url_for('home'))  # 未登入則跳轉到登入頁面
    
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        
        # 獲取當前用戶
        user = users_collection.find_one({'_id': ObjectId(session['user_id'])})
        
        # 檢查舊密碼是否正確
        if not check_password_hash(user['password'], old_password):
            flash('Old password is incorrect.')
            return redirect(url_for('change_password'))
        
        # 檢查新密碼是否一致
        if new_password != confirm_password:
            flash('New passwords do not match.')
            return redirect(url_for('change_password'))
        
        # 密碼加密
        hashed_password = generate_password_hash(new_password)
        
        # 更新密碼
        users_collection.update_one({'_id': ObjectId(session['user_id'])}, {'$set': {'password': hashed_password}})
        
        flash('Password updated successfully.')
        return redirect(url_for('profile'))
    
    return render_template('change_password.html')

if __name__ == '__main__':
    app.run(debug=True)
