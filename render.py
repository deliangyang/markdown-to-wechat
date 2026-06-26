import sys

from sync import render_markdown

if __name__ == '__main__':
    from dataclasses import dataclass
    @dataclass
    class Args:
        path: str = ""
        math: bool = True
        mermaid: bool = True
        code: bool = False
        show_original: bool = False
    with open(sys.argv[1], 'r') as fr:
        print(render_markdown(fr.read(), Args()))