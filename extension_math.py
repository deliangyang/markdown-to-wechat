from markdown.extensions import Extension
import os
import re
import time
from tempfile import NamedTemporaryFile
from urllib.parse import quote
import subprocess
from upload_file import upload_file


class MathToImageExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(
            MathToImagePreprocessor(md), 'mathToImage', 28)


class MathToImagePreprocessor:
    def __init__(self, md):
        self.md = md

    def run(self, lines):
        new_lines = []
        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for $$...$$ display math (multi-line)
            if line.strip().startswith('$$'):
                math_blocks = [line]
                # Check if it closes on the same line
                if line.strip().count('$$') >= 2:
                    # $$...$$ on one line
                    i += 1
                    self._process_math_block(math_blocks, new_lines)
                    continue
                # Multi-line: collect until closing $$
                i += 1
                while i < len(lines):
                    math_blocks.append(lines[i])
                    if lines[i].strip().endswith('$$') and lines[i].strip() != '$$':
                        break
                    i += 1
                self._process_math_block(math_blocks, new_lines)
                i += 1
                continue

            # Check for $...$ inline math
            result_line = self._process_inline_math(line)
            new_lines.append(result_line)
            i += 1

        return new_lines

    def _process_inline_math(self, line):
        """Process all inline $...$ math in a line."""
        if line.strip().startswith('```'):
            return line

        text_parts = self._split_with_placeholders(line)
        if len(text_parts) == 1:
            return line

        # Extract math expressions
        math_exprs = self._extract_math_from_line(line)
        if not math_exprs:
            return line

        result = []
        math_idx = 0
        for part in text_parts:
            if part == 'MATH_PLACEHOLDER':
                if math_idx < len(math_exprs):
                    url = self._render_math(math_exprs[math_idx], display=False)
                    result.append('![%s](%s)' % (math_exprs[math_idx], url))
                    math_idx += 1
                else:
                    result.append('')
            else:
                result.append(part)

        return ''.join(result)

    def _split_with_placeholders(self, line):
        """Split line into text parts and math placeholders."""
        if line.strip().startswith('```'):
            return [line]

        parts = []
        i = 0
        in_math = False
        current = ''

        while i < len(line):
            if line[i] == '$' and (i == 0 or line[i-1] != '\\'):
                if i + 1 < len(line) and line[i+1] == '$':
                    current += line[i:i+2]
                    i += 2
                    continue
                if not in_math:
                    in_math = True
                    if current:
                        parts.append(current)
                        current = ''
                    parts.append('MATH_PLACEHOLDER')
                    i += 1
                else:
                    in_math = False
                    i += 1
            elif in_math:
                current += line[i]
                i += 1
            else:
                current += line[i]
                i += 1

        if current and not in_math:
            parts.append(current)
        elif current and in_math:
            # Unclosed math, treat as literal
            parts.append('$' + current)

        return parts if parts else [line]

    def _extract_math_from_line(self, line):
        """Extract inline math expressions from a line."""
        if line.strip().startswith('```'):
            return []

        math_exprs = []
        i = 0
        in_math = False
        current = ''

        while i < len(line):
            if line[i] == '$' and (i == 0 or line[i-1] != '\\'):
                if i + 1 < len(line) and line[i+1] == '$':
                    i += 2
                    continue
                if not in_math:
                    in_math = True
                    current = ''
                    i += 1
                else:
                    in_math = False
                    if current.strip():
                        math_exprs.append(current.strip())
                    i += 1
            elif in_math:
                current += line[i]
                i += 1
            else:
                i += 1

        return math_exprs

    def _process_math_block(self, math_blocks, new_lines):
        """Process a $$...$$ display math block."""
        # Strip $$ markers
        math_lines = []
        for ml in math_blocks:
            stripped = ml.strip()
            if stripped.startswith('$$'):
                stripped = stripped[2:]
            if stripped.endswith('$$') and len(stripped) >= 2:
                stripped = stripped[:-2]
            math_lines.append(stripped)

        math_content = '\n'.join(math_lines).strip()
        if math_content:
            url = self._render_math(math_content, display=True)
            new_lines.append('![%s](%s)' % (math_content, url))

    def _render_math(self, math_expr, display=False):
        """Render a math expression to an image using headless Chrome + KaTeX."""
        display_mode = 'true' if display else 'false'
        font_size = '24' if display else '16'

        # Escape for JS
        js_safe = math_expr.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')

        html_content = '''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<style>
  body { margin: 0; padding: 8px; background: white; }
  #math { font-size: %spx; padding: 4px 0; }
</style>
</head>
<body>
<div id="math"></div>
<script>
  try {
    katex.render('%s', document.getElementById('math'), {
      displayMode: %s,
      throwOnError: false,
      output: 'html'
    });
  } catch(e) {
    document.getElementById('math').textContent = 'Error: ' + e.message;
  }
</script>
</body>
</html>''' % (font_size, js_safe, display_mode)

        tmp_html = '/tmp/math_%s.html' % str(time.time()).replace('.', '')
        tmp_png = '/tmp/math_%s.png' % str(time.time()).replace('.', '')

        try:
            with open(tmp_html, 'w', encoding='utf-8') as f:
                f.write(html_content)

            # Calculate window size based on content length
            char_count = len(math_expr)
            width = min(1200, max(300, char_count * 12 + 40))
            height = 120 if display else 60

            result = subprocess.run(
                'google-chrome --headless --disable-gpu --no-sandbox '
                '--screenshot=%s --window-size=%d,%d '
                '--virtual-time-budget=3000 file://%s' % (
                    tmp_png, width, height, tmp_html),
                shell=True, capture_output=True, timeout=30)

            if result.returncode != 0 or not os.path.exists(tmp_png):
                print('Chrome render failed: %s' % math_expr)
                # Fallback: return a text placeholder
                return 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"><text y="20" font-size="14">%s</text></svg>' % quote(math_expr)

            url = upload_file(tmp_png)
            return url
        except Exception as e:
            print('Math render error: %s, %s' % (math_expr, e))
            return 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg"><text y="20" font-size="14">render_failed</text></svg>'
        finally:
            if os.path.exists(tmp_html):
                os.unlink(tmp_html)
            if os.path.exists(tmp_png):
                os.unlink(tmp_png)
