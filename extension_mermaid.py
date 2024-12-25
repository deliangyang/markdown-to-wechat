from markdown.extensions import Extension
import os
from tempfile import NamedTemporaryFile


class MermaidToImageExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(MermaidToImagePreprocessor(md), 'mermaidToImage', 27)

class MermaidToImagePreprocessor:
    def __init__(self, md):
        self.md = md


    def run(self, lines):
        new_lines = []
        mermaid = []
        print(lines)
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
                        print('\n'.join(mermaid))
                        cmd = 'mmdc -e png -o /tmp/mermaid.png -i %s' % f.name
                        print(cmd)
                        os.system(cmd)
                    mermaid = []
                else:
                    new_lines.append(line)
            else:
                if len(mermaid) > 0:
                    mermaid.append(line)
                else:
                    new_lines.append(line)
        print('-'*20, new_lines)
        return new_lines