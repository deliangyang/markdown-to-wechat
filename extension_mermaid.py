from markdown.extensions import Extension
import os
from tempfile import NamedTemporaryFile
from upload_file import upload_file
import time


def _extract_mermaid_caption(lines):
    """从 mermaid 块第一行 %% 注释提取图片下方说明。"""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith('%%'):
            text = stripped[2:].strip()
            if '%%' in text:
                text = text.split('%%', 1)[0].strip()
            return text
        break
    return ''


class MermaidToImageExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(
            MermaidToImagePreprocessor(md), 'mermaidToImage', 27)


class MermaidToImagePreprocessor:
    def __init__(self, md):
        self.md = md

    def run(self, lines):
        new_lines = []
        mermaid = []
        for line in lines:
            if line.strip().startswith('```mermaid'):
                mermaid.append(line)
            elif line.strip().startswith('```'):
                # mermaid.append(line)
                if len(mermaid) > 0:
                    del mermaid[0]
                    with NamedTemporaryFile(delete=False, mode='w') as f:
                        f.write('\n'.join(mermaid))
                        f.close()
                        output = '/tmp/%s.png' % str(time.time()
                                                     ).replace('.', '')
                        cmd = 'mmdc -o %s -i %s' % (output, f.name)
                        print(cmd)
                        os.system(cmd)
                        url = upload_file(output)
                        caption = _extract_mermaid_caption(mermaid)
                        new_lines.append('![%s](%s)' % (caption, url))
                        os.unlink(output)
                    mermaid = []
                else:
                    new_lines.append(line)
            else:
                if len(mermaid) > 0:
                    mermaid.append(line)
                else:
                    new_lines.append(line)
        return new_lines
