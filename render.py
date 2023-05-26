import sys

from sync import render_markdown

if __name__ == '__main__':
    with open(sys.argv[1], 'r') as fr:
        print(render_markdown(fr.read()))