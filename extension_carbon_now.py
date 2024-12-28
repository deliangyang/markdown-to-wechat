from markdown.extensions import Extension
import os
from tempfile import NamedTemporaryFile
from upload_file import upload_file
import time

class CarbonNowExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(CarbonNowPreprocessor(md), 'carbonNow', 26)

class CarbonNowPreprocessor:
    def __init__(self, md):
        self.md = md

    def run(self, lines):
        new_lines = []
        carbon_now = []
        for line in lines:
            if len(carbon_now) == 0 and line.strip().startswith('```'):
                carbon_now.append(line)
            elif line.strip().startswith('```'):
                # carbon_now.append(line)
                if len(carbon_now) > 0:
                    del carbon_now[0]
                    with NamedTemporaryFile(delete=False, mode='w') as f:
                        f.write('\n'.join(carbon_now))
                        f.close()
                        print('\n'.join(carbon_now))
                        output = '/tmp/%s.png' % str(time.time()).replace('.', '')
                        cmd = 'carbon-now %s --save-to %s' % (f.name, output)
                        print(cmd)
                        os.system(cmd)
                        url = upload_file(output)
                        new_lines.append('![%s](%s)' % (output, url))
                        os.unlink(output)
                    carbon_now = []
                else:
                    new_lines.append(line)
            else:
                if len(carbon_now) > 0:
                    carbon_now.append(line)
                else:
                    new_lines.append(line)
        return new_lines
