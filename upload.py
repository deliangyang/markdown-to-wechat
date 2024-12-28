import os
from flask import Flask, request
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads'
DOMAIN = 'http://image.ranchulin.com/'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/', methods=['POST'])
def upload_file():
    if request.method != 'POST':
        raise ValueError('Only POST method is allowed')
    if 'file' not in request.files:
        return {
            'message': 'No file part'
        }
    file = request.files['file']
    if file.filename == '':
        return {
            'message': 'No selected file'
        }
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        store_name = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        dir = os.path.dirname(store_name)
        if not os.path.exists(dir):
            os.makedirs(dir)
        file.save(store_name)
        return {
            'filename': DOMAIN +filename,
            'message': 'File uploaded successfully'
        }
    return {
        'message': 'File not allowed'
    }