import sys
from core import *
from git_helper import *
from collections import defaultdict


def _get_java_package_name_from_path(path):
    if not path:
        return None
    if not path.endswith('.java') or not 'com' in path or not 'src/main/java/' in path:
        return None
    return '.'.join(''.join(path[path.index('src/main/java/') + 14:]).replace('.java', '').split('/'))


def _get_methods_line_range(methods):
    res = []
    if not methods:
        return res
    for i, m in enumerate(methods):
        if not m.method_body or not m.method_body['raw']:
            continue
        res.append((i, m.method_body['raw'][0][0], m.method_body['raw'][-1][0]))
    return res


def _get_diff_line_range_map(methods_line_range, diff_lines):
    if not methods_line_range or not diff_lines:
        return {}
    start_index = 0
    diff_line_range_map = {}
    for line in diff_lines:
        for i, line_range in enumerate(methods_line_range[start_index:]):
            if line < line_range[1]:
                break
            if line_range[1] <= line <= line_range[2]:
                diff_line_range_map[line] = line_range[0]
                start_index += i
                break
    return diff_line_range_map


def _is_line_invoked_method(line):
    if not line:
        return False
    line = QUOTE_REGEX.sub('', line)
    line = SINGLE_QUOTE_REGEX.sub('', line)
    return all(e in line for e in ['(', ')', '.'])


def _is_line_null_processed(line_info):
    if not line_info:
        return False
    raw_line = line_info['raw_line']
    var_index = line_info['var_index']
    line_spt = line_info['line_spt']
    var_name = line_spt[var_index]
    raw_line = raw_line.replace(' ', '')
    raw_line = SINGLE_QUOTE_REGEX.sub('', QUOTE_REGEX.sub('', raw_line))

    if '=' in raw_line and '==' not in raw_line and '!=' not in raw_line and var_name in raw_line:
        return not _is_line_invoked_method(''.join(raw_line[raw_line.index('=') + 1:]))
    if 'Exception' in raw_line or 'Throwable' in raw_line:
        return True

    if 'if' not in raw_line:
        return False

    if any(x in raw_line for x in
           ['==null',
            'null==',
            '!=null',
            'null!=',
            'isBlank(%s)' % var_name,
            'usEmpty(%s)' % var_name]) and var_name in raw_line:
        return True

    return False


def _is_line_may_invoke_null_pointer(line_info):
    if not line_info:
        return False
    var_index = line_info['var_index']
    line_spt = line_info['line_spt']
    raw_line = line_info['raw_line']
    sep = map(lambda x: x.strip(), line_info['separated'])

    if 'for' in line_spt and ':' in sep and var_index > sep.index(':'):
        return True
    if '%s.' % line_spt[var_index] in raw_line:
        return True
    return False


def _analyse_method_diff_null_pointer_helper(method, changed_lines):
    if not method or not changed_lines:
        return {}

    var_processed_map = {}
    var_processed_reversed_map = {}
    all_vars = method.method_body['local_vars'].copy()
    for var_name, var_info in all_vars.items():
        if 'line_info' not in var_info:
            continue
        line_info = var_info['line_info']
        for info in line_info:
            if _is_line_may_invoke_null_pointer(info):
                var_processed_reversed_map[info['line_index']] = var_name

    for var_name, var_info in all_vars.items():
        if 'line_info' not in var_info:
            continue
        line_info = var_info['line_info']
        for info in line_info:
            if _is_line_null_processed(info):
                var_processed_map[var_name] = info['line_index']
                break

    changed_reversed_map = {k: v for k, v in var_processed_reversed_map.items() if k in changed_lines}
    un_processed_map = {k: v for k, v in changed_reversed_map.items() if v not in var_processed_map
                        or var_processed_map[v] > k}
    return un_processed_map


def _analyse_method_diff_null_pointer(change_method_group, entity):
    if not change_method_group or not entity:
        return {}
    res = defaultdict(dict)
    for method_index, changed_lines in change_method_group.items():
        method_res = _analyse_method_diff_null_pointer_helper(entity.methods[method_index], changed_lines)
        res['%s~%s' % (entity.name, entity.methods[method_index].method_name)].update(method_res)
    return {k: v for k, v in res.items() if v}


def _process_null_pointer_from_entity(entity, diff_lines):
    if not entity or not diff_lines:
        return {}
    methods_line_range = _get_methods_line_range(entity.methods)
    diff_line_range_map = _get_diff_line_range_map(methods_line_range, diff_lines)
    change_method_group = {}
    for k, v in diff_line_range_map.items():
        if v not in change_method_group:
            change_method_group[v] = []
        change_method_group[v] += [k]
    return _analyse_method_diff_null_pointer(change_method_group, entity)


def process_null_pointer(class_map, diff_map):
    res = {}
    if not class_map or not diff_map:
        return res
    for k, v in diff_map.items():
        java_pack_name = _get_java_package_name_from_path(k)
        if not java_pack_name:
            continue
        entity = class_map[java_pack_name]
        null_pointer_map = _process_null_pointer_from_entity(entity, v)
        if null_pointer_map:
            res[java_pack_name] = null_pointer_map
    return {k: v for k, v in res.items() if v}


def main():
    if len(sys.argv) < 2:
        logging.error('Please input the branch needs to be checked')
        sys.exit(-1)
    if len(sys.argv) < 3:
        logging.error('Please then input the analyse project dir')
        sys.exit(-1)
    branch_name = sys.argv[1]
    proj_dir = sys.argv[2]
    if not branch_name or not proj_dir:
        logging.error('branch name or project directory is none')
        sys.exit(-1)
    diff_map = diff_against_master(branch_name, proj_dir)
    class_map = get_proj_class_map(proj_dir)
    setup_class_map_method_dep(class_map)
    process_res = process_null_pointer(class_map, diff_map)
    print('Analyse null pointer result:')
    for k, v in process_res.items():
        print('-' * 100)
        print(k)
        for method_name, var_info in v.items():
            print('\t%s:' % method_name)
            for line, var_name in sorted(var_info.items()):
                print('\t\t%s: %s' % (line, var_name))


if __name__ == '__main__':
    main()
