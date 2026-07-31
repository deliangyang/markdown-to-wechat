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
import time
import urllib
import urllib.request
from datetime import datetime, timedelta
import argparse
import argparse
from dataclasses import dataclass
import webbrowser
from pathlib import Path
import requests
import markdown
import requests
from dotenv import load_dotenv
from markdown.extensions import codehilite
from pyquery import PyQuery
from werobot import WeRoBot
from PIL import Image
from extension_mermaid import MermaidToImageExtension
from extension_block_quote import BlockQuoteExtension
from extension_carbon_now import CarbonNowExtension
from extension_math import MathToImageExtension


re_p_img = re.compile(r"<p>\s*(<img [^>]+>)\s*</p>")


@dataclass
class SyncArgs:
    path: str
    only_render: bool = False
    mermaid: bool = True
    math: bool = True
    code: bool = False
    open_browser: bool = False
    show_original: bool = False
    only_word_count: bool = False

    def __post_init__(self):
        if not os.path.exists(self.path) or not os.path.isfile(self.path):
            raise FileNotFoundError(f"Markdown file '{self.path}' does not exist.")


def parse_arguments() -> SyncArgs:
    parser = argparse.ArgumentParser(description="Sync markdown to wechat")
    parser.add_argument("path", type=str, help="path of markdown file")
    parser.add_argument(
        "-r", "--only-render", action="store_true", help="only render markdown"
    )
    parser.add_argument(
        "-m", "--mermaid", action="store_true", help="convert mermaid to image"
    )
    parser.add_argument(
        "--math", default=True, help="convert math formulas to image (default: True)"
    )
    parser.add_argument(
        "--no-math", action="store_false", dest="math", help="disable math rendering"
    )
    parser.add_argument(
        "-c", "--code", action="store_true", help="convert code to image"
    )
    parser.add_argument(
        "-o", "--open-browser", action="store_true", help="open browser after sync"
    )
    parser.add_argument(
        "-s",
        "--show-original",
        action="store_true",
        help="show original markdown content",
    )
    parser.add_argument(
        "-w",
        "--only-word-count",
        action="store_true",
        help="only count words in markdown",
    )
    args = parser.parse_args()
    return SyncArgs(
        path=args.path,
        only_render=args.only_render,
        mermaid=args.mermaid,
        math=args.math,
        code=args.code,
        open_browser=args.open_browser,
        show_original=args.show_original,
        only_word_count=args.only_word_count,
    )


reg_title = re.compile(r"^#\s*(.*)")

load_dotenv()  # take environment variables from .env.
image_upload_endpoint = os.getenv("IMAGE_UPLOAD_ENDPOINT")
CACHE = {}
CACHE_STORE = os.getenv("CACHE_STORE")
POST_DIR = os.getenv("POST_DIR")


def get_script_dir():
    return os.path.dirname(os.path.abspath(__file__))


def dump_cache():
    fp = open("{}/{}".format(get_script_dir(), CACHE_STORE), "wb")
    pickle.dump(CACHE, fp)


def init_cache():
    global CACHE
    if os.path.exists(f"{get_script_dir()}/{CACHE_STORE}"):
        fp = open("{}/{}".format(get_script_dir(), CACHE_STORE), "rb")
        CACHE = pickle.load(fp)
        # print(CACHE)
        return
    dump_cache()


class NewClient:
    def __init__(self):
        self.__accessToken = ""
        self.__leftTime = 0

    def __real_get_access_token(self):
        postUrl = (
            "https://api.weixin.qq.com/cgi-bin/token?grant_type="
            "client_credential&appid=%s&secret=%s"
            % (os.getenv("WECHAT_APP_ID"), os.getenv("WECHAT_APP_SECRET"))
        )
        urlResp = urllib.request.urlopen(postUrl)
        urlResp = json.loads(urlResp.read())
        self.__accessToken = urlResp["access_token"]
        self.__leftTime = urlResp["expires_in"]

    def get_access_token(self):
        if self.__leftTime < 10:
            self.__real_get_access_token()
        return self.__accessToken


def Client():
    robot = WeRoBot()
    robot.config["APP_ID"] = os.getenv("WECHAT_APP_ID")
    robot.config["APP_SECRET"] = os.getenv("WECHAT_APP_SECRET")
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
    with open(file_path, "rb") as f:
        md5.update(f.read())
    return md5.hexdigest()


def cache_update(file_path):
    digest = file_digest(file_path)
    CACHE[digest] = "{}:{}".format(file_path, datetime.now())
    dump_cache()


def file_processed(file_path):
    digest = file_digest(file_path)
    return cache_get(digest) != None


def strip_aigc_metadata(image_path: str) -> str:
    """
    重新编码图片，去除 AIGC / EXIF / PNG text 等元数据后返回临时文件路径。
    失败时回退为原路径。
    """
    try:
        img = Image.open(image_path)
        fmt = (img.format or "").upper()
        clean = Image.new(img.mode, img.size)
        clean.putdata(list(img.getdata()))

        name = os.path.basename(image_path)
        root, ext = os.path.splitext(name)
        if not ext:
            ext = ".png" if fmt == "PNG" else ".jpg"
        out_path = "/tmp/stripped_{}{}".format(root, ext)

        if fmt in ("JPEG", "JPG") or ext.lower() in (".jpg", ".jpeg"):
            if clean.mode != "RGB":
                clean = clean.convert("RGB")
            clean.save(out_path, "JPEG", quality=95)
        elif fmt == "WEBP" or ext.lower() == ".webp":
            clean.save(out_path, "WEBP")
        else:
            # PNG 及其他：不传 pnginfo，丢弃 AIGC 等 text chunk
            clean.save(out_path, "PNG")
        print("stripped aigc metadata: {} => {}".format(image_path, out_path))
        return out_path
    except Exception as e:
        print("strip aigc metadata failed, use original: {}".format(e))
        return image_path


def upload_image_from_path(image_path):
    # 上传前去掉 AIGC 等元数据
    image_path = strip_aigc_metadata(image_path)
    image_digest = file_digest(image_path)
    res = cache_get(image_digest)
    if res != None:
        return res[0], res[1]
    client, _ = Client()
    print("uploading image {}".format(image_path))
    try:
        media_json = client.upload_permanent_media(
            "image", open(image_path, "rb")
        )  # 永久素材
        media_id = media_json["media_id"]
        media_url = media_json["url"]
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
    name = img_url.split("/")[-1]
    f_name = "/tmp/{}".format(name)
    if "." not in f_name:
        f_name = f_name + ".png"
    with requests.get(img_url) as response:
        with open(f_name, "wb") as f:
            f.write(response.content)
    return upload_image_from_path(f_name)


re_md_image = re.compile(r"!\[.*?\]\(([^)]+)\)")


def extract_markdown_image(line: str):
    """从一行中提取 markdown 图片路径，支持列表项包裹。"""
    match = re_md_image.search(line.strip())
    if match:
        return match.group(1).strip()
    return None


def get_image_under_title(content: str):
    """
    获取一级标题正下方的第一张图片路径/URL；不存在则返回 None。
    标题与图片之间允许空行；图片可写在列表项中，如 `- ![](x.png)`。
    """
    lines = content.split("\n")
    found_title = False
    for line in lines:
        stripped = line.strip()
        if not found_title:
            if reg_title.match(stripped):
                found_title = True
            continue
        if not stripped:
            continue
        image = extract_markdown_image(stripped)
        if image:
            return image
        # 标题下首个非空行不是图片，则放弃
        break
    return None


def remove_image_under_title(content: str) -> str:
    """
    从正文中移除一级标题正下方用作封面的那一行图片（含列表项包裹），
    封面只用于 thumb，不再出现在生成的 HTML 中。
    """
    lines = content.split("\n")
    found_title = False
    result = []
    removed = False
    for line in lines:
        stripped = line.strip()
        if not found_title:
            result.append(line)
            if reg_title.match(stripped):
                found_title = True
            continue
        if removed:
            result.append(line)
            continue
        if not stripped:
            result.append(line)
            continue
        if extract_markdown_image(stripped):
            removed = True
            continue
        result.append(line)
        removed = True
    return "\n".join(result)


def get_images_from_markdown(content):
    lines = content.split("\n")
    images = []
    for line in lines:
        image = extract_markdown_image(line)
        if image:
            images.append(image)
    return images


re_upload_images = re.compile(r'src="(%s[^"]+)"' % image_upload_endpoint)


def get_upload_images(content: str) -> list[str]:
    matches = re_upload_images.findall(content)
    if matches:
        return list(map(lambda x: x, matches))
    return []


def fetch_attr(content: str, key: str) -> str:
    """
    从 markdown 文件中提取属性
    """
    lines = content.split("\n")
    for line in lines:
        if line.startswith(key):
            return line.split(":")[1].strip()
    return ""


def render_markdown(content, args={}):
    exts = [
        "markdown.extensions.extra",
        "markdown.extensions.tables",
        "markdown.extensions.toc",
        "markdown.extensions.sane_lists",
        "markdown.extensions.smarty",
        BlockQuoteExtension(),
    ]
    if args.math:
        exts.append(MathToImageExtension())
    if args.mermaid:
        exts.append(MermaidToImageExtension())
    if args.code:
        exts.append(CarbonNowExtension())
    exts.append(
        codehilite.makeExtension(
            guess_lang=False, noclasses=True, pygments_style="monokai"
        )
    )

    html = markdown.markdown(content, extensions=exts)
    print("-" * 100)
    if args.show_original:
        print(html)
    print("-" * 100)
    open(f"{get_script_dir()}/origin.html", "w").write(html)
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
    pre = ""
    for line in content.split("\n"):
        if line.startswith("<p>"):
            if pre.startswith("<blockquote>"):
                line = line.replace("<p>", gen_css("blockquote"))
            else:
                if re_p_img.match(line):
                    line = re_p_img.sub(r"\1", line)
                else:
                    line = line.replace("<p>", gen_css("para"))
        if line.startswith("<blockquote>"):
            line = line.replace(
                "<blockquote>",
                '<blockquote style="word-spacing: 0px; word-break: break-word;font-size:14px;text-align:left;border-left:7px solid #DBDBDB; padding-left:5px;margin-left:10px;">',
            )
        pre = line
        res.append(line)
    return "\n".join(res)


def gen_css(path, *args):
    template = open("{}/assets/{}.tmpl".format(get_script_dir(), path), "r").read().strip()
    return template.format(*args)


def replace_header(content):
    res = []
    for line in content.split("\n"):
        l = line.strip()
        if l.startswith("<h") and l.endswith(">") > 0:
            tag = l.split(" ")[0].replace("<", "")
            value = l.split(">")[1].split("<")[0]
            if tag == "h2":
                res.append(gen_css("sub_h2", value))
            elif tag == "h3":
                res.append(gen_css("sub_h3", value))
            else:
                digit = tag[1]
                font = (
                    (18 + (4 - int(tag[1])) * 2)
                    if (digit >= "0" and digit <= "9")
                    else 18
                )
                res.append(gen_css("sub", tag, font, value, tag))
        else:
            res.append(line)
    return "\n".join(res)


def replace_links(content):
    pq = PyQuery(open("{}/origin.html".format(get_script_dir())).read())
    links = pq("a")
    refs = []
    index = 1
    if len(links) == 0:
        return content
    for l in links.items():
        link = gen_css("link", l.text(), index)
        index += 1
        refs.append([l.attr("href"), l.text(), link])

    for r in refs:
        orig = '<a href="{}">{}</a>'.format(html.escape(r[0]), r[1])
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


re_img_tag = re.compile(r"<img\s+([^>]+?)\s*/?\s*>", re.IGNORECASE)
IMG_STYLE = "max-width:100%;height:auto;display:block;margin:0 auto;padding:0;border:0;vertical-align:top;"


def fix_image(content: str) -> str:
    def repl(match):
        attrs = match.group(1)
        alt_m = re.search(r'\balt="([^"]*)"', attrs)
        src_m = re.search(r'\bsrc="([^"]*)"', attrs)
        if not src_m:
            return match.group(0)
        alt_text = alt_m.group(1) if alt_m else ""
        src_url = src_m.group(1)
        img = '<img alt="{}" src="{}" style="{}" />'.format(
            alt_text, src_url, IMG_STYLE
        )
        if alt_text.strip():
            return gen_css("figure", img, alt_text)
        return '<section style="margin:0 0 16px;padding:0;text-align:center;line-height:0;font-size:0;">{}</section>'.format(
            img
        )

    return re_img_tag.sub(repl, content)


UL_MARKERS = ("•", "◦", "▪")
LIST_ITEM_STYLE = (
    "margin:0 0 10px;padding-left:{pad}px;font-size:15px;line-height:1.8;"
    "text-align:left;color:#374151;word-spacing:0;word-break:break-word;"
)
LIST_MARKER_STYLE = (
    "display:inline-block;min-width:1.6em;margin-right:2px;"
    "font-weight:600;color:#059669;"
)
re_label_item = re.compile(r"^[A-Za-z][A-Za-z0-9_\s\-+/\.&]*[：:]")


def _li_plain_text(li) -> str:
    parts = []
    if li.text:
        parts.append(li.text)
    for child in li:
        if child.tag in ("ul", "ol"):
            continue
        parts.append("".join(child.itertext()))
        if child.tail:
            parts.append(child.tail)
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _is_list_intro(text: str) -> bool:
    text = text.strip()
    if text.endswith("：") or text.endswith(":"):
        return True
    for suffix in ("以下几类", "如下", "包括", "分别是", "主要有"):
        if text.endswith(suffix) or text.endswith(suffix + "："):
            return True
    return False


def _looks_like_sub_item(text: str) -> bool:
    text = text.strip()
    if re_label_item.match(text):
        return True
    if len(text) <= 40:
        return True
    if len(text) <= 64 and text.count("，") <= 1:
        return True
    return False


def _restructure_flat_list(list_el) -> None:
    from lxml.html import Element

    lis = [li for li in list_el if li.tag == "li"]
    if len(lis) < 2:
        return

    i = 0
    while i < len(lis):
        li = lis[i]
        if li.getparent() is not list_el:
            i += 1
            continue

        plain = _li_plain_text(li)
        if not _is_list_intro(plain) or i + 1 >= len(lis):
            i += 1
            continue

        sub_lis = []
        j = i + 1
        while j < len(lis):
            sub_li = lis[j]
            if sub_li.getparent() is not list_el:
                break
            if _looks_like_sub_item(_li_plain_text(sub_li)):
                sub_lis.append(sub_li)
                j += 1
            else:
                break

        if not sub_lis:
            i += 1
            continue

        nested = Element(list_el.tag)
        for sub_li in sub_lis:
            nested.append(sub_li)
        li.append(nested)
        lis = [child for child in list_el if child.tag == "li"]
        i += 1


def _render_list_items(list_el, depth: int = 1) -> list[str]:
    tag = list_el.tag
    html_parts = []
    pad = 16 + (depth - 1) * 28
    idx = 1

    for li in list_el:
        if li.tag != "li":
            continue

        content_parts = []
        nested_lists = []
        if li.text and li.text.strip():
            content_parts.append(li.text.strip())
        for child in li:
            if child.tag in ("ul", "ol"):
                nested_lists.append(child)
            else:
                from lxml.etree import tostring

                content_parts.append(
                    tostring(child, encoding="unicode", method="html")
                )
            if child.tail and child.tail.strip():
                content_parts.append(child.tail.strip())
        content = "".join(content_parts).strip()

        if tag == "ol":
            marker = "{}.".format(idx)
            idx += 1
        else:
            marker = UL_MARKERS[min(depth - 1, len(UL_MARKERS) - 1)]

        if content:
            html_parts.append(
                '<p style="{}">'
                '<span style="{}">{}</span>{}</p>'.format(
                    LIST_ITEM_STYLE.format(pad=pad),
                    LIST_MARKER_STYLE,
                    marker,
                    content,
                )
            )

        for nested in nested_lists:
            html_parts.extend(_render_list_items(nested, depth + 1))

    return html_parts


def fix_lists(content: str) -> str:
    from lxml.etree import tostring
    from lxml.html import document_fromstring, fragment_fromstring

    doc = document_fromstring('<div id="__lists_root__">' + content + "</div>")
    root = doc.xpath("//div[@id='__lists_root__']")[0]

    while True:
        all_lists = root.xpath(".//ul | .//ol")
        if not all_lists:
            break
        top_lists = [
            el
            for el in all_lists
            if el.getparent() is not None
            and el.getparent().tag not in ("ul", "ol")
        ]
        if not top_lists:
            break
        for list_el in top_lists:
            parent = list_el.getparent()
            idx = parent.index(list_el)
            _restructure_flat_list(list_el)
            depth = len(list_el.xpath("ancestor::ul | ancestor::ol")) + 1
            for i, frag_html in enumerate(_render_list_items(list_el, depth)):
                parent.insert(idx + i, fragment_fromstring(frag_html))
            parent.remove(list_el)

    return "".join(
        tostring(child, encoding="unicode", method="html") for child in root
    )


re_codeblock = re.compile(
    r'(<div class="codehilite"[^>]*>\s*<pre[^>]*>)(.*?)(</pre>\s*</div>)',
    re.DOTALL,
)
CODE_PRE_STYLE = (
    "line-height:1.6;color:#F8F8F2;font-size:12px;margin:0;padding:8px;"
    "white-space:pre;word-wrap:normal;word-break:normal;"
    "overflow-x:auto;overflow-y:hidden;-webkit-overflow-scrolling:touch;"
    "font-family:'SF Mono',Consolas,Monaco,monospace;"
)
CODE_IN_PRE_STYLE = (
    "display:block;white-space:pre;word-wrap:normal;word-break:normal;"
    "overflow-x:auto;-webkit-overflow-scrolling:touch;"
    "font-family:inherit;font-size:inherit;color:inherit;"
)


def _preserve_code_spaces(body: str) -> str:
    """将代码块文本中的空格和制表符转为不可折叠字符，保留缩进。"""
    parts = re.split(r"(<[^>]+>)", body)
    for i in range(0, len(parts), 2):
        parts[i] = parts[i].replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;").replace(
            " ", "&nbsp;"
        )
    return "".join(parts)


def fix_code_blocks(content: str) -> str:
    """微信公众号不保留 pre 内换行，需转为 br 并设置 white-space。"""

    def repl(match):
        head, body, tail = match.groups()
        head = re.sub(
            r"<pre[^>]*>",
            '<pre style="{}">'.format(CODE_PRE_STYLE),
            head,
            count=1,
        )
        body = re.sub(
            r"<code(?![^>]*style=)([^>]*)>",
            r'<code style="{}"\1>'.format(CODE_IN_PRE_STYLE),
            body,
            count=1,
        )
        body = body.replace("\n", "<br>\n")
        body = _preserve_code_spaces(body)
        return head + body + tail

    return re_codeblock.sub(repl, content)


def format_fix(content):
    content = content.replace("</li>\n", "</li>")
    # content = content.replace('<li>', '<li style="display:block;">')
    content = content.replace("background: #272822", gen_css("code"))
    content_x = ""
    for line in content.split("\n"):
        if line.find("<pre") < 0 and line.find("<code>") >= 0:
            content_x += (
                re.sub(
                    r"<code>([^<]+)</code>",
                    r'<code style="%s">\1</code>' % gen_css("line_code"),
                    line,
                )
                + "\n"
            )
        else:
            content_x += line + "\n"
    content = content_x
    content = fix_code_blocks(content)
    return content


def css_beautify(content):
    content = fix_strong(content)
    content = fix_em_dash(content)
    content = replace_para(content)
    content = replace_header(content)
    content = replace_links(content)
    content = format_fix(content)
    content = fix_lists(content)
    content = fix_image(content)
    content = gen_css("header") + content + gen_css("end") + gen_css("footer_cta") + "</section>"
    content = fix_escape_tag_php(content)
    return content


reg_b = re.compile(r"<b>([^<]+)</b>")
reg_strong = re.compile(r"<strong>([^<]+)</strong>")


def fix_strong(content: str):
    style = gen_css("strong")
    content = reg_b.sub(r'<b style="%s">「\1 」</b>' % style, content)
    content = reg_strong.sub(r'<strong style="%s">\1</strong>' % style, content)
    return content


re_code_block = re.compile(r"(<(?:code|pre)[^>]*>.*?</(?:code|pre)>)", re.DOTALL)


def fix_em_dash(content: str):
    style = gen_css("em_dash")
    span = '<span style="%s">——</span>' % style
    parts = re_code_block.split(content)
    for i in range(0, len(parts), 2):
        parts[i] = parts[i].replace("——", span)
    return "".join(parts)


def fix_escape_tag_php(content: str):
    content = content.replace("&lt;?php", "&#60;&quest;php")
    return content


def upload_media_news(args: SyncArgs):
    """
    上传到微信公众号素材
    """
    content = open(args.path, "r").read()
    TITLE = fetch_attr(content, "title").strip('"').strip("'")
    gen_cover = fetch_attr(content, "gen_cover").strip('"')
    images = get_images_from_markdown(content)
    # 标题下方有图时，直接用作封面，不再从外部随机获取
    cover_image = get_image_under_title(content)
    print(images)
    print(TITLE)
    print("cover_image:", cover_image)
    if cover_image:
        if cover_image in images:
            images.remove(cover_image)
        images = [cover_image] + images
        # 封面图只用于 thumb，从正文中去掉
        content = remove_image_under_title(content)
    elif len(images) == 0 or gen_cover == "true":
        letters = string.ascii_lowercase
        seed = "".join(random.choice(letters) for i in range(10))
        images = ["https://picsum.photos/seed/" + seed + "/400/600"] + images
    uploaded_images = {}

    THUMB_MEDIA_ID = ""
    if not args.only_render:
        for image in images:
            media_id = ""
            media_url = ""
            if image.startswith("http"):
                media_id, media_url = upload_image(image)
            else:
                _path = os.path.dirname(args.path) + "/"
                media_id, media_url = upload_image_from_path(_path + image)
            if media_id != None:
                uploaded_images[image] = [media_id, media_url]

        content = update_images_urls(content, uploaded_images)

        THUMB_MEDIA_ID = (len(images) > 0 and uploaded_images[images[0]][0]) or ""
    AUTHOR = os.getenv("AUTHOR")

    _, filename = os.path.split(args.path)
    title = filename.replace(".md", "")
    title_match = reg_title.match(content.strip())
    if title_match:
        title = title_match.group(1)
        content = content.replace(title_match.group(0), "")

    markdown_content = render_markdown(content, args)
    # upload extra images
    if not args.only_render:
        extra_images = list(
            filter(
                lambda x: x.startswith(image_upload_endpoint),
                get_upload_images(markdown_content),
            )
        )
        for image in extra_images:
            media_id, media_url = upload_image(image)
            uploaded_images[image] = [media_id, media_url]
            markdown_content = markdown_content.replace(image, media_url)
        # link = os.path.basename(post_path).replace('.md', '')
    digest = fetch_attr(markdown_content, "subtitle").strip().strip('"').strip("'")

    print(filename)
    articles = {
        "articles": [
            {
                "title": title,
                "thumb_media_id": THUMB_MEDIA_ID,
                "author": AUTHOR,
                #"digest": '',
                "show_cover_pic": 1,
                "content": markdown_content,
                "content_source_url": "",
                "need_open_comment": 1,
            }
            # 若新增的是多图文素材，则此处应有几段 articles 结构，最多 8 段
        ]
    }
    fp = open("{}/result.html".format(get_script_dir()), "w")
    fp.write(markdown_content)
    fp.close()

    if args.only_render:
        return

    client = NewClient()
    token = client.get_access_token()
    headers = {"Content-type": "text/plain; charset=utf-8"}
    post_data = json.dumps(articles, ensure_ascii=False).encode("utf-8")

    postUrl = "https://api.weixin.qq.com/cgi-bin/draft/add?access_token=%s" % token
    r = requests.post(postUrl, data=post_data, headers=headers)
    print(r.text)
    resp = json.loads(r.text)
    print(resp)
    media_id = resp["media_id"]
    cache_update(args.path)
    return resp


def run(args: SyncArgs):
    # string_date = "2023-03-13"
    # print(string_date)
    content = open(args.path, "r").read()
    date = fetch_attr(content, "date").strip()
    if file_processed(args.path):
        print("{} has been processed".format(args.path))
        # return
    print("-" * 20, args.path, "-" * 20)
    news_json = upload_media_news(args)
    print(news_json)
    print("successful")


def date_range(start_date, end_date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def markdown_word_count_exclude_tags(file: str) -> int:
    """
    计算 markdown 文件的字数，排除代码块和图片等标签
    """
    content = open(file, "r").read()
    # 移除 title
    content = re.sub(r"^#\s*.*", "", content, flags=re.MULTILINE)
    # 移除代码块
    content = re.sub(r"```[\s\S]*?```", "", content)
    # 移除图片标签
    content = re.sub(r"!\[.*?\]\(.*?\)", "", content)
    # 移除 HTML 标签
    content = re.sub(r"<[^>]+>", "", content)
    # 计算字数
    words = re.findall(r"\b\w+\b", content)
    total = 0
    for word in words:
        if re.match(r"^[\u4e00-\u9fa5]$", word):
            total += 1
        else:
            total += len(word)
    return total


if __name__ == "__main__":
    args = parse_arguments()
    if args.only_word_count:
        count = markdown_word_count_exclude_tags(args.path)
        print(f"Word count (excluding code blocks and images): {count}")
        exit(0)
    print("begin sync to wechat")
    init_cache()
    start_time = time.time()  # 开始时间

    run(args)
    # for x in date_range(datetime.now() - timedelta(days=7), datetime.now() + timedelta(days=2)):
    #     print("start time: {}".format(x.strftime("%m/%d/%Y, %H:%M:%S")))
    #     string_date = x.strftime('%Y-%m-%d')
    #     print(string_date)

    end_time = time.time()  # 结束时间
    print("程序耗时%f秒。" % (end_time - start_time))
    if args.open_browser:
        webbrowser.open("result.html")
