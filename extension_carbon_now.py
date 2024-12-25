from markdown.extensions import Extension
import os
from tempfile import NamedTemporaryFile

class CarbonNowExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(CarbonNowPreprocessor(md), 'carbonNow', 26)

class CarbonNowPreprocessor:
    def __init__(self, md):
        self.md = md

    def run(self, lines):
        new_lines = []
        carbon_now = []
        print('x'*100, lines)
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
                        cmd = 'carbon-now %s --save-to %s' % (f.name, '/tmp/carbon.png')
                        print(cmd)
                        os.system(cmd)
                    carbon_now = []
                else:
                    new_lines.append(line)
            else:
                if len(carbon_now) > 0:
                    carbon_now.append(line)
                else:
                    new_lines.append(line)
        print('-'*20, new_lines)
        return new_lines
