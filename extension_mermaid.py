from markdown.extensions import Extension
import os
from tempfile import NamedTemporaryFile
from upload_file import upload_file
import time


class MermaidToImageExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(MermaidToImagePreprocessor(md), 'mermaidToImage', 27)

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
                        output = '/tmp/%s.png' % str(time.time()).replace('.', '')
                        cmd = 'mmdc -o %s -i %s' % (output, f.name)
                        print(cmd)
                        os.system(cmd)
                        url = upload_file(output)
                        new_lines.append('![%s](%s)' % ('mermaid', url))
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