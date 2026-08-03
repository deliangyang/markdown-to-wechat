from markdown.extensions import Extension
import re

re_html_tag = re.compile(r'\\\<([^>]+)>')
re_bold = re.compile(r'\*\*(.+?)\*\*|__(.+?)__')


def format_inline(text):
    text = re_bold.sub(lambda m: '<strong>%s</strong>' % (m.group(1) or m.group(2)), text)
    return text


class BlockQuoteExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(BlockQuotePreprocessor(md), 'blockquote', 27)


class BlockQuotePreprocessor:
    def __init__(self, md):
        self.md = md

    def __get_style(self, ident):
        return 'font-size:14px;text-align:left;word-spacing: 0px; word-break:normal;overflow-wrap:break-word;border-left:7px solid #DBDBDB; padding-left:5px;margin-left:%spx;' % int(ident * 8)

    def run(self, lines):
        new_lines = []
        block_quotes = []
        lines_len = len(lines)
        ident = 0
        for (idx, line) in enumerate(lines):
            lstrip_line = str(line).lstrip()
            ident = len(line) - len(lstrip_line)
            if lstrip_line.startswith('>'):
                quote_text = format_inline(re_html_tag.sub(r'&lt;\1&gt;', lstrip_line[1:]))
                block_quotes.append('<i style="display:block;font-size:14px;font-weight:400;">%s</i>' %
                                    quote_text)
                if idx + 1 < lines_len:
                    next_lstrip_line = str(lines[idx + 1]).lstrip()
                    next_ident = len(lines[idx + 1]) - len(next_lstrip_line)
                    if not next_lstrip_line.startswith('>') or next_ident != ident:
                        new_lines.append('<blockquote style="%s">' %
                                         self.__get_style(ident))
                        new_lines.extend(block_quotes)
                        new_lines.append('</blockquote>')
                        block_quotes = []
            else:
                new_lines.append(line)
        if len(block_quotes) > 0:
            new_lines.append('<blockquote style="%s">' %
                             self.__get_style(ident))
            new_lines.extend(block_quotes)
            new_lines.append('</blockquote>')
        return new_lines
