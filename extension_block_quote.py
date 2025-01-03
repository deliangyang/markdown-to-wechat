from markdown.extensions import Extension
import re

re_html_tag = re.compile(r'\\\<([^>]+)>')

class BlockQuoteExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(BlockQuotePreprocessor(md), 'blockquote', 27)

class BlockQuotePreprocessor:
    def __init__(self, md):
        self.md = md

    def __get_style(self, ident):
        return 'font-size:14px;text-align:left;word-spacing: 0px; word-break: break-word;border-left:7px solid #DBDBDB; padding-left:5px;margin-left:%spx;' % int(ident * 8)

    def run(self, lines):
        new_lines = []
        blockquotes = []
        lines_len = len(lines)
        ident = 0
        for (idx, line) in enumerate(lines):
            lstriped_line = str(line).lstrip()
            ident = len(line) - len(lstriped_line)
            if lstriped_line.startswith('>'):
                blockquotes.append('<i style="display:block;font-size:14px;font-weight:400;">%s</i>' % re_html_tag.sub(r'&lt;\1&gt;', lstriped_line[1:]))
                if idx + 1 < lines_len:
                    next_lstriped_line = str(lines[idx + 1]).lstrip()
                    next_ident = len(lines[idx + 1]) - len(next_lstriped_line)
                    if not next_lstriped_line.startswith('>') or next_ident != ident:
                        new_lines.append('<blockquote style="%s">' % self.__get_style(ident))
                        new_lines.extend(blockquotes)
                        new_lines.append('</blockquote>')
                        blockquotes = []
            else:
                new_lines.append(line)
        if len(blockquotes) > 0:
            new_lines.append('<blockquote style="%s">' % self.__get_style(ident))
            new_lines.extend(blockquotes)
            new_lines.append('</blockquote>')
        return new_lines
