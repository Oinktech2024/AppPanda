from flask import Flask, request, render_template_string
import dropbox
from pymongo import MongoClient
from datetime import datetime
from dotenv import load_dotenv
import os

app = Flask(__name__)
load_dotenv()

# Dropbox 設定
DROPBOX_ACCESS_TOKEN = os.getenv('DROPBOX_TOKEN')
dbx = dropbox.Dropbox(DROPBOX_ACCESS_TOKEN)

# MongoDB 連接設置
APPLICATIONS_MONGO_URL = os.getenv('APPLICATIONS_MONGO_URL')
client = MongoClient(APPLICATIONS_MONGO_URL)
db = client['applicationsdb']
uploads_collection = db['uploads']

DEFAULT_UPLOADER_NAME = "Admin"

@app.route('/')
def index():
    form_html = '''
        <h1>上傳檔案到 Dropbox</h1>
        <p>請選擇要上傳的檔案，並提供相應的應用資訊。上傳後，檔案將被儲存到 Dropbox 並且記錄到資料庫。</p>
        <form action="/upload" method="post" enctype="multipart/form-data">
            <label for="file">選擇檔案:</label><br>
            <input type="file" id="file" name="file" onchange="showForm()" required>
            <small>請上傳 .exe、.ipa、或 .apk 檔案。其他格式會被分類為「其他」類型。</small><br><br>

v id="form-section"             <distyle="display:none;">
                <h2>應用資訊</h2>
                <label for="version">版本:</label><br>
                <input type="text" id="version" name="version" required>
                <small>請輸入應用的版本號，例如 1.0.0。</small><br><br>

                <label for="app_name">應用名稱:</label><br>
                <input type="text" id="app_name" name="app_name" required>
                <small>請輸入應用的名稱，這將用於檔案記錄。</small><br><br>

                <label for="app_tags">應用標籤 (用逗號分隔):</label><br>
                <input type="text" id="app_tags" name="app_tags" required>
                <small>請用逗號分隔每個標籤，例如「教育,遊戲,生產力」。</small><br><br>

                <label for="uploader_name">上傳者名稱:</label><br>
                <input type="text" id="uploader_name" name="uploader_name" value="{{ uploader_name }}" readonly>
                <small>這是您的上傳者名稱，無法更改。</small><br><br>

                <label for="app_type">應用類型:</label><br>
                <input type="text" id="app_type" name="app_type" readonly>
                <small>根據檔案類型自動設定，如 iOS、Android、Windows。</small><br><br>

                <button type="submit">上傳</button>
            </div>
        </form>
        <p><a href="/search">前往搜尋頁面</a>，查找已上傳的檔案。</p>

        <script>
            function showForm() {
                var fileInput = document.getElementById('file');
                var file = fileInput.files[0];
                var fileExtension = file.name.split('.').pop().toLowerCase();

                document.getElementById('form-section').style.display = 'block';
                var appType = '';

                if (fileExtension === 'ipa') {
                    appType = 'iOS';
                } else if (fileExtension === 'apk') {
                    appType = 'Android';
                } else if (fileExtension === 'exe') {
                    appType = 'Windows';
                } else {
                    appType = 'Other';
                }

                document.getElementById('app_type').value = appType;
            }
        </script>
    '''
    return render_template_string(form_html, uploader_name=DEFAULT_UPLOADER_NAME)

@app.route('/upload', methods=['POST'])
def upload_file():
    version = request.form['version']
    app_name = request.form['app_name']
    app_tags = request.form['app_tags']
    uploader_name = request.form['uploader_name']
    app_type = request.form['app_type']

    if 'file' not in request.files:
        return "未找到檔案部分，請重新選擇檔案", 400

    file = request.files['file']

    if file.filename == '':
        return "未選擇檔案，請重新選擇檔案", 400

    uid = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    filename = f"{uploader_name}_{uid}_{file.filename}"
    file_extension = filename.split('.')[-1].lower()

    if file_extension == 'exe':
        folder = 'exe_files'
    elif file_extension == 'ipa':
        folder = 'ipa_files'
    elif file_extension == 'apk':
        folder = 'apk_files'
    else:
        folder = 'other_files'

    dropbox_path = f'/{folder}/{filename}'
    dbx.files_upload(file.read(), dropbox_path, mode=dropbox.files.WriteMode.overwrite)

    upload_data = {
        'filename': filename,
        'version': version,
        'app_name': app_name,
        'app_tags': app_tags.split(','),
        'uploader_name': uploader_name,
        'app_type': app_type,
        'upload_date': datetime.utcnow(),
        'dropbox_path': dropbox_path
    }
    uploads_collection.insert_one(upload_data)

    return f'''
        <h2>檔案 {filename} 已成功上傳至 Dropbox！</h2>
        <p><strong>版本:</strong> {version}</p>
        <p><strong>應用名稱:</strong> {app_name}</p>
        <p><strong>應用標籤:</strong> {app_tags}</p>
        <p><strong>上傳者名稱:</strong> {uploader_name}</p>
        <p><strong>應用類型:</strong> {app_type}</p>
        <p><a href="/">返回上傳頁面</a></p>
    ''', 200

@app.route('/search')
def search_page():
    keyword = request.args.get('keyword', '').strip()
    query = {}

    # 如果提供了關鍵字，進行搜尋
    if keyword:
        query = {
            "$or": [
                {"filename": {"$regex": keyword, "$options": "i"}},
                {"app_tags": {"$regex": keyword, "$options": "i"}},
                {"uploader_name": {"$regex": keyword, "$options": "i"}}
            ]
        }
        uploads = uploads_collection.find(query)
    else:
        # 如果沒有關鍵字，顯示搜尋表單及提示訊息
        return '''
            <h1>搜尋檔案</h1>
            <p>請輸入關鍵字以搜尋檔案，可以根據檔案名稱、標籤或上傳者名稱進行搜尋。</p>
            <form method="get" action="/search">
                <label for="keyword">關鍵字:</label>
                <input type="text" id="keyword" name="keyword" placeholder="輸入關鍵字">
                <button type="submit">搜尋</button>
            </form>
            <p>請輸入關鍵字進行搜尋。</p>
            <p><a href="/">返回上傳頁面</a></p>
        '''

    # 顯示搜尋結果
    search_html = '''
        <h1>搜尋檔案</h1>
        <p>您搜尋的關鍵字: <strong>{}</strong></p>
        <form method="get" action="/search">
            <label for="keyword">關鍵字:</label>
            <input type="text" id="keyword" name="keyword" value="{}" placeholder="輸入關鍵字">
            <button type="submit">搜尋</button>
        </form>
    '''.format(keyword, keyword)

    # 檢查搜尋結果
    if uploads_collection.count_documents(query) == 0:
        search_html += "<p>未找到相關檔案。請嘗試使用其他關鍵字。</p>"
    else:
        search_html += "<h2>搜尋結果</h2><ul>"
        for upload in uploads:
            uploader_name = upload.get('uploader_name', 'Unknown')
            if 'dropbox_path' in upload:
                download_link = f"/download?path={upload['dropbox_path']}"
                search_html += f"<li>{upload['filename']} (上傳者: {uploader_name}) - <a href='{download_link}'>下載</a></li>"
            else:
                search_html += f"<li>{upload['filename']} (上傳者: {uploader_name}) - <em>無可用下載鏈接</em></li>"
        search_html += '</ul>'

    search_html += '<p><a href="/">返回上傳頁面</a></p>'
    return search_html


@app.route('/download')
def download_file():
    dropbox_path = request.args.get('path')
    if not dropbox_path:
        return "未指定檔案路徑", 400

    try:
        metadata, res = dbx.files_download(dropbox_path)
        response = app.response_class(res.content, mimetype='application/octet-stream')
        response.headers['Content-Disposition'] = f'attachment; filename={metadata.name}'
        return response
    except dropbox.exceptions.ApiError as e:
        return f"下載檔案時出現錯誤: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)
