from pathlib import Path
content = '''from planner_app import app

if __name__ == '__main__':
    app.run(debug=True)
'''
Path('app.py').write_text(content, encoding='utf-8')
