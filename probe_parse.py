from pathlib import Path
from reassure.core.parser import detect_language, parse_file, get_language
p = Path('tests/fixtures/sample_repo/src/api/routes.py')
print('exists', p.exists())
print('detect_language', detect_language(p))
res = parse_file(p)
print('parse_file is None?', res is None)
if res is not None:
    tree, src = res
    print('tree type:', type(tree))
    print('source len', len(src))
print('get_language:', get_language('python'))
