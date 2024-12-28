import requests
import dotenv
import os

dotenv.load_dotenv()

image_upload_endpoint = os.getenv('IMAGE_UPLOAD_EDPOINT')

def upload_file(file_path):
    global image_upload_endpoint
    with open(file_path, 'rb') as f:
        files = {'file': f}
        r = requests.post(image_upload_endpoint, files=files)
        return r.json()['filename']