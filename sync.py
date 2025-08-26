#!/usr/bin/python3
# public/upload_news.py
# -*- coding: utf-8 -*-
"""
推送文章到微信公众号
"""
import hashlib
import html
import json
import os
import pickle
import random
import re
import string
import sys
import time
import urllib
import urllib.request
from datetime import date, datetime, timedelta
import argparse

import markdown
import requests
from dotenv import load_dotenv
from markdown.extensions import codehilite
from pyquery import PyQuery
from werobot import WeRoBot
from extension_mermaid import MermaidToImageExtension
from extension_block_quote import BlockQuoteExtension
from extension_carbon_now import CarbonNowExtension

re_title = re.compile(r'^#\s*(.*)')

load_dotenv()  # take environment variables from .env.
image_upload_endpoint = os.getenv('IMAGE_UPLOAD_EDPOINT')

CACHE = {}

CACHE_STORE = os.getenv('CACHE_STORE')
POST_DIR = os.getenv('POST_DIR')

def get_script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def dump_cache():
    fp = open(CACHE_STORE, "wb")
    pickle.dump(CACHE, fp)


def init_cache():
    global CACHE
    if os.path.exists(CACHE_STORE):
        fp = open(CACHE_STORE, "rb")
        CACHE = pickle.load(fp)
        # print(CACHE)
        return
    dump_cache()


class NewClient:

    def __init__(self):
        self.__accessToken = ''
        self.__leftTime = 0

    def __real_get_access_token(self):
        postUrl = ("https://api.weixin.qq.com/cgi-bin/token?grant_type="
                   "client_credential&appid=%s&secret=%s" % (os.getenv('WECHAT_APP_ID'), os.getenv('WECHAT_APP_SECRET')))
        urlResp = urllib.request.urlopen(postUrl)
        urlResp = json.loads(urlResp.read())
        self.__accessToken = urlResp['access_token']
        self.__leftTime = urlResp['expires_in']

    def get_access_token(self):
        if self.__leftTime < 10:
            self.__real_get_access_token()
        return self.__accessToken


def Client():
    robot = WeRoBot()
    robot.config["APP_ID"] = os.getenv('WECHAT_APP_ID')
    robot.config["APP_SECRET"] = os.getenv('WECHAT_APP_SECRET')
    client = robot.client
    token = client.grant_token()
    return client, token


def cache_get(key):
    if key in CACHE:
        return CACHE[key]
    return None


def file_digest(file_path):
    """
    计算文件的 md5 值
    """
    md5 = hashlib.md5()
    with open(file_path, 'rb') as f:
        md5.update(f.read())
    return md5.hexdigest()


def cache_update(file_path):
    digest = file_digest(file_path)
    CACHE[digest] = "{}:{}".format(file_path, datetime.now())
    dump_cache()


def file_processed(file_path):
    digest = file_digest(file_path)
    return cache_get(digest) != None


def upload_image_from_path(image_path):
    image_digest = file_digest(image_path)
    res = cache_get(image_digest)
    if res != None:
        return res[0], res[1]
    client, _ = Client()
    print("uploading image {}".format(image_path))
    try:
        media_json = client.upload_permanent_media(
            "image", open(image_path, "rb"))  # 永久素材
        media_id = media_json['media_id']
        media_url = media_json['url']
        CACHE[image_digest] = [media_id, media_url]
        dump_cache()
        print("file: {} => media_id: {}".format(image_path, media_id))
        return media_id, media_url
    except Exception as e:
        print("upload image error: {}".format(e))
        return None, None


def upload_image(img_url):
    """
    * 上传临时素菜
    * 1、临时素材 media_id 是可复用的。
    * 2、媒体文件在微信后台保存时间为 3 天，即 3 天后 media_id 失效。
    * 3、上传临时素材的格式、大小限制与公众平台官网一致。
    """
    resource = urllib.request.urlopen(img_url)
    name = img_url.split("/")[-1]
    f_name = "/tmp/{}".format(name)
    if "." not in f_name:
        f_name = f_name + ".png"
    with open(f_name, 'wb') as f:
        f.write(resource.read())
    return upload_image_from_path(f_name)


def get_images_from_markdown(content):
    lines = content.split('\n')
    images = []
    for line in lines:
        line = line.strip()
        if line.startswith('![') and line.endswith(')'):
            image = line.split('(')[1].split(')')[0].strip()
            images.append(image)
    return images

re_upload_images = re.compile(r'src="(%s[^"]+)"' % image_upload_endpoint)

def get_upload_images(content)-> list[str]:
    matches = re_upload_images.findall(content)
    if matches:
        return list(map(lambda x: x, matches))
    return []


def fetch_attr(content, key):
    """
    从 markdown 文件中提取属性
    """
    lines = content.split('\n')
    for line in lines:
        if line.startswith(key):
            return line.split(':')[1].strip()
    return ""


def render_markdown(content, args={}):
    exts = [
        'markdown.extensions.extra',
        'markdown.extensions.tables',
        'markdown.extensions.toc',
        'markdown.extensions.sane_lists',
        'markdown.extensions.smarty',
        BlockQuoteExtension(),
    ]
    if args.mermaid:
        exts.append(MermaidToImageExtension())
    if args.code:
        exts.append(CarbonNowExtension())
    exts.append(codehilite.makeExtension(
        guess_lang=False,
        noclasses=True,
        pygments_style='monokai'
    ))

    html = markdown.markdown(content, extensions=exts)
    print('-' * 100)
    print(html)
    print('-' * 100)
    open("origi.html", "w").write(html)
    return css_beautify(html)


def update_images_urls(content, uploaded_images):
    for image, meta in uploaded_images.items():
        orig = "({})".format(image)
        new = "({})".format(meta[1])
        # print("{} -> {}".format(orig, new))
        content = content.replace(orig, new)
    return content


def replace_para(content):
    res = []
    pre = ''
    for line in content.split("\n"):
        if line.startswith("<p>"):
            if pre.startswith('<blockquote>'):
                line = line.replace("<p>", gen_css("blockquote"))
            else:
                line = line.replace("<p>", gen_css("para"))
        if line.startswith('<blockquote>'):
            line = line.replace(
                '<blockquote>', '<blockquote style="word-spacing: 0px; word-break: break-word;font-size:14px;text-align:left;border-left:7px solid #DBDBDB; padding-left:5px;margin-left:10px;">')
        pre = line
        res.append(line)
    return "\n".join(res)


def gen_css(path, *args):
    tmpl = open("{}/assets/{}.tmpl".format(get_script_dir(), path), "r").read()
    return tmpl.format(*args)


def replace_header(content):
    res = []
    for line in content.split("\n"):
        l = line.strip()
        if l.startswith("<h") and l.endswith(">") > 0:
            tag = l.split(' ')[0].replace('<', '')
            value = l.split('>')[1].split('<')[0]
            digit = tag[1]
            font = (18 + (4 - int(tag[1])) *
                    2) if (digit >= '0' and digit <= '9') else 18
            res.append(gen_css("sub", tag, font, value, tag))
        else:
            res.append(line)
    return "\n".join(res)


def replace_links(content):
    pq = PyQuery(open('origi.html').read())
    links = pq('a')
    refs = []
    index = 1
    if len(links) == 0:
        return content
    for l in links.items():
        link = gen_css("link", l.text(), index)
        index += 1
        refs.append([l.attr('href'), l.text(), link])

    for r in refs:
        orig = "<a href=\"{}\">{}</a>".format(html.escape(r[0]), r[1])
        content = content.replace(orig, r[2])
    content = content + "\n" + gen_css("ref_header")
    content = content + """<section class="footnotes">"""
    index = 1
    for r in refs:
        l = r[2]
        line = gen_css("ref_link", index, r[1], r[0])
        index += 1
        content += line + "\n"
    content = content + "</section>"
    return content


def fix_image(content):
    pq = PyQuery(open('origi.html').read())
    imgs = pq('img')
    for line in imgs.items():
        link = """<img alt="{}" src="{}" />""".format(
            line.attr('alt'), line.attr('src'))
        figure = gen_css("figure", link, line.attr('alt'))
        content = content.replace(link, figure)
    return content


def format_fix(content):
    content = content.replace("<ul>\n<li>", '<ul style="margin-left:1em"><li>')
    content = content.replace("</li>\n</ul>", "</li></ul>")
    content = content.replace(
        "<ol>\n<li>", "<ol style=\"margin-left: 20px;\"><li>")
    content = content.replace("</li>\n</ol>", "</li></ol>")
    content = content.replace('</li>\n', '</li>')
    # content = content.replace('<li>', '<li style="display:block;">')
    content = content.replace("background: #272822", gen_css("code"))
    contenxt_x = ''
    for line in content.split('\n'):
        if line.find('<pre') < 0 and line.find('<code>') >= 0:
            contenxt_x += re.sub(r'<code>([^<]+)</code>',
                                 r'<code style="%s">\1</code>' % gen_css("line_code"), line) + '\n'
        else:
            contenxt_x += line + '\n'
    content = contenxt_x
    # content = content.replace("<code>", '<code style="%s">' % gen_css("code"))
    content = content.replace("""<pre style="line-height: 125%">""",
                              """<pre style="line-height: 125%; color: white; font-size: 11px;">""")
    return content


def css_beautify(content):
    content = fix_strong(content)
    content = replace_para(content)
    content = replace_header(content)
    content = replace_links(content)
    content = format_fix(content)
    content = fix_image(content)
    content = gen_css("header") + content + "</section>"
    content = fix_escape_tag_php(content)
    return content


reg_strong = re.compile(r'<b>([^<]+)</b>')


def fix_strong(content):
    content = reg_strong.sub(r'<b style="%s">「\1 」</b>' %
                             gen_css("strong"), content)
    return content


def fix_escape_tag_php(content):
    content = content.replace("&lt;?php", '&#60;&quest;php')
    return content


def upload_media_news(post_path, only_render=False, args={}):
    """
    上传到微信公众号素材
    """
    content = open(post_path, 'r').read()
    TITLE = fetch_attr(content, 'title').strip('"').strip('\'')
    gen_cover = fetch_attr(content, 'gen_cover').strip('"')
    images = get_images_from_markdown(content)
    print(images)
    print(TITLE)
    if len(images) == 0 or gen_cover == "true":
        letters = string.ascii_lowercase
        seed = ''.join(random.choice(letters) for i in range(10))
        print(seed)
        images = ["https://picsum.photos/seed/" + seed + "/400/600"] + images
    uploaded_images = {}

    THUMB_MEDIA_ID = ''
    if not only_render:
        for image in images:
            media_id = ''
            media_url = ''
            if image.startswith("http"):
                media_id, media_url = upload_image(image)
            else:
                _path = os.path.dirname(post_path) + '/'
                media_id, media_url = upload_image_from_path(_path + image)
            if media_id != None:
                uploaded_images[image] = [media_id, media_url]

        content = update_images_urls(content, uploaded_images)

        THUMB_MEDIA_ID = (
            len(images) > 0 and uploaded_images[images[0]][0]) or ''
    AUTHOR = os.getenv('AUTHOR')

    _, filename = os.path.split(post_path)
    title = filename.replace('.md', '')
    title_match = re_title.match(content)
    if title_match:
        title = title_match.group(1)
        content = content.replace(title_match.group(0), '')

    markdowned_content = render_markdown(content, args)
    # upload extra images
    if not args.only_render:
        extra_iamges = list(filter(lambda x: x.startswith(image_upload_endpoint), get_upload_images(markdowned_content)))
        for image in extra_iamges:
            media_id, media_url = upload_image(image)
            uploaded_images[image] = [media_id, media_url]
            markdowned_content = markdowned_content.replace(image, media_url)
        # link = os.path.basename(post_path).replace('.md', '')
    digest = fetch_attr(markdowned_content, 'subtitle').strip().strip('"').strip('\'')

    print(filename)
    articles = {
        'articles':
        [
            {
                "title": title,
                "thumb_media_id": THUMB_MEDIA_ID,
                "author": AUTHOR,
                "digest": digest,
                "show_cover_pic": 1,
                "content": markdowned_content,
                "content_source_url": '',
                "need_open_comment": 1,
            }
            # 若新增的是多图文素材，则此处应有几段 articles 结构，最多 8 段
        ]
    }
    fp = open('./result.html', 'w')
    fp.write(markdowned_content)
    fp.close()

    if only_render:
        return

    client = NewClient()
    token = client.get_access_token()
    headers = {'Content-type': 'text/plain; charset=utf-8'}
    datas = json.dumps(articles, ensure_ascii=False).encode('utf-8')

    postUrl = "https://api.weixin.qq.com/cgi-bin/draft/add?access_token=%s" % token
    r = requests.post(postUrl, data=datas, headers=headers)
    print(r.text)
    resp = json.loads(r.text)
    print(resp)
    media_id = resp['media_id']
    cache_update(post_path)
    return resp


def run(path_str, only_render=False, args={}):
    # string_date = "2023-03-13"
    # print(string_date)
    content = open(path_str, 'r').read()
    date = fetch_attr(content, 'date').strip()
    if file_processed(path_str):
        print("{} has been processed".format(path_str))
        # return
    print('-' * 20, path_str, '-' * 20)
    news_json = upload_media_news(path_str, only_render, args)
    print(news_json)
    print('successful')


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def usage():
    parser = argparse.ArgumentParser(description='Sync markdown to wechat')
    parser.add_argument('path', type=str, help='path of markdown file')
    parser.add_argument('-r', '--only-render', action='store_true',
                        help='only render markdown')
    parser.add_argument('-m', '--mermaid', action='store_true',
                        help='convert mermaid to image')
    parser.add_argument('-c', '--code', action='store_true',
                        help='convert code to image')
    return parser.parse_args()


if __name__ == '__main__':
    args = usage()
    print("begin sync to wechat")
    init_cache()
    start_time = time.time()  # 开始时间
    run(args.path, args.only_render, args)
    # for x in daterange(datetime.now() - timedelta(days=7), datetime.now() + timedelta(days=2)):
    #     print("start time: {}".format(x.strftime("%m/%d/%Y, %H:%M:%S")))
    #     string_date = x.strftime('%Y-%m-%d')
    #     print(string_date)

    end_time = time.time()  # 结束时间
    print("程序耗时%f秒。" % (end_time - start_time))
