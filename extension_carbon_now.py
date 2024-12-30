from markdown.extensions import Extension
import os
from tempfile import NamedTemporaryFile
from upload_file import upload_file
import time
import subprocess

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
                        output = '%s' % str(time.time()).replace('.', '')
                        cmd = 'carbon-now %s --config .carbon-now.json --engine chromium --skip-display --save-to /tmp --save-as %s' % (f.name, output)
                        print(cmd)
                        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE)
                        if result.returncode != 0:
                            raise Exception('Failed to run carbon-now ' + str(result.stdout))
                        tmp_name = '/tmp/%s.png' % output
                        url = upload_file(tmp_name)
                        new_lines.append('![%s](%s)' % ('image', url))
                        os.unlink(tmp_name)
                        if os.path.exists('carbon.png'):
                            os.unlink('carbon.png')
                    carbon_now = []
                else:
                    new_lines.append(line)
            else:
                if len(carbon_now) > 0:
                    carbon_now.append(line)
                else:
                    new_lines.append(line)
        return new_lines
