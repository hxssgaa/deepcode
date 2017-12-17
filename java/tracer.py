# -*- coding: utf-8 -*-

import json
import sys
from collections import defaultdict

from core import *

TOP_DEP_KEY = 'TopDep'


def _show_dep_helper(dep, level, simplify):
    if not dep:
        return []
    res = []
    prev_space = '\t|' * level
    for k, v in dep.items():
        res.append('%s%s:' % (prev_space, k[k.rindex('.') + 1:] if '.' in k and simplify else k))
        sub = _show_dep_helper(v, level + 1, simplify)
        if sub:
            res += sub
    return res


def _simplify_dep(dep):
    if not dep:
        return dep
    res = {}
    for k, v in dep.items():
        if '.' in k:
            res[k[k.rindex('.') + 1:]] = _simplify_dep(v)
    return res


def _get_dep_count_helper(dep, dep_count_map):
    if not dep or dep_count_map is None:
        return
    for k, v in dep.items():
        dep_count_map[k] += 1
        _get_dep_count_helper(v, dep_count_map)


def _get_top_dep(dep, top_dep_n):
    d = defaultdict(int)
    _get_dep_count_helper(dep, d)
    items = sorted(map(lambda x: (x[1], x[0]), d.items()), reverse=True)
    return map(lambda x: '%s,%s' % (x[1], x[0]), items[:top_dep_n])


def _show_dep(dep, simplify=False, print_info=False, write_info=False, top_dep_n=None):
    if not dep:
        return ''
    if simplify:
        dep = _simplify_dep(dep)
    if top_dep_n:
        top_dep_res = _get_top_dep(dep, top_dep_n)
        dep[TOP_DEP_KEY] = top_dep_res
    res = json.dumps(dep, indent=4, sort_keys=True)
    if print_info:
        print(res)
    if write_info:
        with open('tracer_result2.json', 'w') as f:
            f.writelines(json.dumps(dep, indent=4, sort_keys=True))
    return res


def trace(start_packages, proj_dir, filter_classes_func=None):
    class_map = get_proj_class_map(proj_dir)
    impl_map = get_impl_map(class_map)
    dep = get_dependency(start_packages, class_map, impl_map)
    if filter_classes_func:
        dep = {k: v for k, v in dep.items() if filter_classes_func(k)}
    _show_dep(dep, simplify=True, write_info=True, top_dep_n=30)


def main():
    if len(sys.argv) < 2:
        logging.error('Please first input the start analyse Java packages.')
        sys.exit(-1)
    if len(sys.argv) < 3:
        logging.error('Please then input the analyse project dir.')
        sys.exit(-1)
    start_package_dirs = sys.argv[1].split(',') if sys.argv[1] else None
    proj_dir = sys.argv[2]
    if not start_package_dirs or not proj_dir:
        logging.error('Analyse Java packages or project dir is empty')
        sys.exit(-1)
    trace(start_package_dirs, proj_dir,
          filter_classes_func=lambda x: 'WdkCartService' in x or
                                        'WdkCartConfirmService' in x or
                                        'WDKCartFuseService' in x or
                                        'WdkCartHgService' in x or
                                        'WdkCartReadService' in x or
                                        'WdkCartWriteService' in x)


if __name__ == '__main__':
    main()
