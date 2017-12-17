# -*- coding: utf-8 -*-

import sys
import random
import string

from core import *

DEFAULT_UT_IMPORT_MAP = {
    'ArrayList': 'java.util',
    'List': 'java.util',
    'Collection': 'java.util',
    'Map': 'java.util',
    'Set': 'java.util',
    'Assert': 'org.junit',
    'Test': 'org.junit',
    'RunWith': 'org.junit.runner',
    'InjectMocks': 'org.mockito',
    'Mock': 'org.mockito',
    'PrepareForTest': 'org.powermock.core.classloader.annotations',
    'PowerMockRunner': 'org.powermock.modules.junit4',
    'any': 'static org.mockito.Matchers',
    'anyListOf': 'static org.mockito.Matchers',
    'when': 'static org.mockito.Mockito',
    'mock': 'static org.powermock.api.mockito.PowerMockito',
    'mockStatic': 'static org.powermock.api.mockito.PowerMockito',
}
UT_TEST_COUNT = 5


def _setup_method_deps_helper(entity, method, visited):
    if not method or not method.method_body or 'external_vars' not in method.method_body or \
            not method.method_body['external_vars']:
        return
    res = method.method_body['external_vars'].values()
    if (method.method_name, len(method.params)) in visited:
        return
    visited.add((method.method_name, len(method.params)))
    method.dep_info = list(res)
    if 'self_methods' in method.method_body and method.method_body['self_methods']:
        self_methods = method.method_body['self_methods']
        mapped_methods = {(e.method_name, len(e.params)): e for e in
                          entity.methods}  # set(map(lambda x: (x.method_name, len(x.params)), entity.methods))
        self_methods &= set(mapped_methods.keys())
        for self_method in self_methods:
            _setup_method_deps_helper(entity, mapped_methods[self_method], visited)
            if 'dep_info' in mapped_methods[self_method].__dict__:
                method.dep_info += mapped_methods[self_method].dep_info
    visited.remove((method.method_name, len(method.params)))


def _setup_method_deps(entity, method):
    _setup_method_deps_helper(entity, method, set())


def _get_instance_name_by_class(class_name):
    if not class_name:
        return class_name
    class_name = class_name.strip()
    if class_name[0].islower() or len(class_name) == 1:
        return class_name
    elif class_name[1].islower():
        return class_name[0].lower() + class_name[1:]
    s = []
    index = 0
    while index < len(class_name) - 1:
        if class_name[index + 1].islower():
            break
        else:
            s.append(class_name[index].lower())
        index += 1
    return '%s%s' % (''.join(s), class_name[index:])


def _get_capital_method_name(method_name):
    if not method_name:
        return method_name
    if len(method_name) == 1:
        return method_name.upper()
    return method_name[0].upper() + ''.join(method_name[1:])


def _get_unique_method_key(method):
    if not method:
        return None
    return '%s(%s)' % (method.method_name, ','.join(sorted(method.params.values()))) \
        if method.params else '%s()' % method.method_name


def _get_object_type(t):
    if not t or t not in PRIMITIVE_TYPE:
        return t
    return {
        'boolean': 'Boolean',
        'byte': 'Byte',
        'char': 'Char',
        'short': 'Short',
        'int': 'Integer',
        'long': 'Long',
        'float': 'Float',
        'double': 'Double',
    }.get(t)


def _get_non_void_invoke_methods(class_type, invoke_methods, class_map):
    if not class_type or not invoke_methods or not class_map or class_type not in class_map:
        return set()
    entity = class_map[class_type]
    return set(filter(lambda x: (x.method_name, len(x.params)) in invoke_methods and x.ret_type != 'void',
                      entity.methods))


def _build_random_string(n):
    if not n or n < 0:
        return ''
    return '"%s"' % ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(n))


def _build_random_num(n, is_long=False):
    if not n or n < 0:
        return ''
    return str(random.randint(0, pow(10, n))) + ('L' if is_long else '')


def _build_random_char():
    return '\'%s\'' % random.choice(string.ascii_lowercase + string.ascii_uppercase)


def _build_random_boolean():
    return random.choice(['true', 'false'])


def _build_random_float():
    return str(random.uniform(0, 2000)) + 'f'


def _build_random_double():
    return str(random.uniform(0, 2000)) + 'lf'


def _build_mock_param_data(class_type, class_map):
    generics = GENERICS_REGEX.match(class_type)
    if generics:
        generics = generics.group(1)
    class_type = clear_generics(class_type)
    if class_type == 'String':
        return _build_random_string(8)
    elif class_type == 'Integer' or class_type == 'Short':
        return _build_random_num(2)
    elif class_type == 'Long':
        return _build_random_num(6, is_long=True)
    elif class_type == 'Char':
        return _build_random_char()
    elif class_type == 'Boolean':
        return _build_random_boolean()
    elif class_type == 'Float':
        return _build_random_float()
    elif class_type == 'Double':
        return _build_random_double()
    else:
        return 'mock(%s.class)' % class_type


def _build_mock_param_code(param_index, param_tup, class_map):
    if param_index is None or not param_tup or not class_map:
        return []
    res = ['\t\t%s param%d = %s;' % (param_tup[0], param_index, _build_mock_param_data(param_tup[0], class_map))]
    return res


def _build_ut_code(entity, class_map, ut_import_map, ut_class_name, public_methods):
    if not entity or not ut_import_map or not ut_class_name or not public_methods:
        return []
    ut_package = entity.package
    package_code = ['package %s;' % ut_package, '']

    # main code
    main_code = ['@RunWith(PowerMockRunner.class)']
    main_code += ['public class %s {' % ut_class_name]

    # dep info
    methods_contain_dep_info = filter(lambda x: 'dep_info' in x.__dict__, public_methods)
    # mocked fields
    mocked_fields_info = set()
    for method in methods_contain_dep_info:
        mocked_fields_info |= {me['class_type'] for me in method.dep_info}
    if '?' in mocked_fields_info:
        mocked_fields_info.remove('?')
    mocked_fields_name_map = {}
    for mocked_field in mocked_fields_info:
        mocked_field_class = mocked_field.split('.')[-1]
        mocked_field_package = '.'.join(mocked_field.split('.')[:-1])
        mocked_field_name = _get_instance_name_by_class(mocked_field_class)
        mocked_fields_name_map[mocked_field] = mocked_field_name
        if not mocked_field_name:
            logging.error('field name empty (%s)' % mocked_field_class)
            continue
        main_code += ['\t@Mock']
        if mocked_field_class not in ut_import_map:
            ut_import_map[mocked_field_class] = mocked_field_package
            main_code += ['\tprivate %s %s;' % (mocked_field_class, mocked_field_name)]
        else:
            main_code += ['\tprivate %s.%s %s;' % (mocked_field_package, mocked_field_class, mocked_field_name)]
    # UT class
    ut_interface = entity.interfaces[0]
    ut_interface_name = ut_interface.split('.')[-1]
    ut_import_map[ut_interface_name] = '.'.join(ut_interface.split('.')[:-1])
    ut_service_instance = _get_instance_name_by_class(ut_interface_name)
    main_code += ['']
    main_code += ['\t@InjectMocks']
    main_code += ['\tprivate %s %s = new %s();' % (ut_interface_name, ut_service_instance, entity.name)]

    main_code += ['']
    # ut functions
    for public_method in public_methods:
        method_signature = '\t%s %s test%sBase_%s(Object[] param)' % (
            ' '.join(public_method.method_types), public_method.ret_type,
            _get_capital_method_name(public_method.method_name),
            '_'.join(public_method.params.keys())
        )
        if public_method.throws:
            method_signature += ' throws %s' % ','.join(public_method.throws)
        external_vars = public_method.method_body[
            'external_vars'] if 'external_vars' in public_method.method_body else []
        external_vars = {k: v for k, v in external_vars.items() if 'class_type' in v and v['class_type'] != '?'}
        external_invoke_methods_map = {k: _get_non_void_invoke_methods(v['class_type'], v['invoke_methods'], class_map)
                                       for k, v in external_vars.items() if 'invoke_methods' in v
                                       and v['invoke_methods']}
        method_signature += ' {'
        main_code += ['\t@SuppressWarnings("unchecked")']
        main_code += [method_signature]
        param_index = 0
        param_type_map = {}
        tab = '\t\t'
        for k, v in external_invoke_methods_map.items():
            for method in v:
                params_mock_any = ', '.join(map(lambda x: '(%s)any(%s.class)' % (x, clear_generics(x)),
                                                method.params.values()))
                ret_type = _get_object_type(method.ret_type)
                main_code += ['%swhen(%s.%s(%s)).thenReturn((%s)%s);' % (tab, k, method.method_name, params_mock_any,
                                                                         ret_type, 'param[%d]' % param_index)]
                param_type_map[param_index] = (ret_type, None)
                param_index += 1

        param_type_map.update({
            param_index + i: (_get_object_type(e), k) for i, (k, e) in enumerate(public_method.params.items())
        })
        ret_params = ', '.join('(%s)param[%d]' % (param_type_map[k][0], k) for k in sorted(
            param_type_map.keys()[param_index:]))
        main_code += ['%s%s %s.%s(%s);' % (tab, '' if public_method.ret_type == 'void' else 'return',
                                           ut_service_instance, public_method.method_name, ret_params)]
        main_code += ['\t}']
        main_code += ['']
        for test_index in range(UT_TEST_COUNT):
            main_code += ['\t@SuppressWarnings("unchecked")']
            main_code += ['\t@Test']
            main_code += ['\tpublic void test%s_%s%d() throws Exception {' % (
                _get_capital_method_name(public_method.method_name),
                '_'.join(public_method.params.keys())
                , test_index + 1)]
            main_code += ['%sList<Object> param = new ArrayList<Object>();' % tab]
            for k in sorted(param_type_map.keys()):
                main_code += _build_mock_param_code(k, param_type_map[k], class_map)
            for k in sorted(param_type_map.keys()):
                main_code += ['%sparam.add(param%d);' % (tab, k)]
            if public_method.ret_type == 'void':
                main_code += ['%stest%sBase_%s(param.toArray());' % (
                    tab, _get_capital_method_name(public_method.method_name),
                    '_'.join(public_method.params.keys())
                )]
            else:
                main_code += ['%s%s result = test%sBase_%s(param.toArray());' % (
                    tab, public_method.ret_type, _get_capital_method_name(public_method.method_name),
                    '_'.join(public_method.params.keys())
                )]
            main_code += ['\t}']
            main_code += ['']

    main_code += ['}']
    import_code = sorted(map(lambda e: 'import %s.%s;' % (e[1], e[0]), ut_import_map.items()))
    import_code += ['']

    return package_code + import_code + main_code


def _ut_gen_build(entity, class_map, impl_map, target_dir, interface_methods=None):
    if not entity or not class_map or not impl_map or not target_dir:
        return
    entity_key = build_java_class_key(entity.package, entity.name)
    if entity.class_type == 1:
        if entity_key not in impl_map:
            return
        impl_entities = impl_map[entity_key]
        _ut_gen_build(class_map[impl_entities[0]], class_map, impl_map, target_dir, interface_methods=entity.methods)
        return

    # By default, the package of ut is the same as the package of test class.
    ut_import_map = DEFAULT_UT_IMPORT_MAP
    ut_class_name = '%sTest' % entity.name

    public_methods = filter(lambda x: 'public' in x.method_types, entity.methods)
    if interface_methods:
        unique_method_keys = {_get_unique_method_key(e) for e in interface_methods}
        public_methods = filter(lambda x: _get_unique_method_key(x) in unique_method_keys, public_methods)
        if len(public_methods) != len(unique_method_keys):
            logging.error('entity(%s) public methods doesn\'t match its interfaces' % entity.name)
    for method in public_methods:
        _setup_method_deps(entity, method)
    res = _build_ut_code(entity, class_map, ut_import_map, ut_class_name, public_methods)
    res = map(lambda x: '%s\n' % x, res)
    test_file_name = '%sTest.java' % entity.name
    with open(os.path.join(target_dir, test_file_name), 'w') as f:
        f.writelines(res)


def _ut_gen_by_package(start_package, class_map, impl_map, target_dir, filter_classes_func=None):
    if not start_package or not class_map or not impl_map or not target_dir:
        return
    for sub_dir in filter(filter_classes_func, get_dir_java_files(start_package)):
        key = get_java_class_entity_key_by_directory(sub_dir)
        if key not in class_map:
            logging.error('%s not in class_map, dir is: %s' % (key, sub_dir))
            return None
        entity = class_map[key]
        _ut_gen_build(entity, class_map, impl_map, target_dir)


def ut_gen(start_packages, proj_dir, target_dir, filter_classes_func=None):
    class_map = get_proj_class_map(proj_dir)
    setup_class_map_method_dep(class_map)
    impl_map = get_impl_map(class_map)
    for package in start_packages:
        _ut_gen_by_package(package, class_map, impl_map, target_dir, filter_classes_func)


def main():
    if len(sys.argv) < 2:
        logging.error('Please first input the Java interface directories which needs UT.')
        sys.exit(-1)
    if len(sys.argv) < 3:
        logging.error('Please then input the analyse project dir.')
        sys.exit(-1)
    if len(sys.argv) < 4:
        logging.error('Please input the target UT directories')
    start_package_dirs = sys.argv[1].split(',') if sys.argv[1] else None
    proj_dir = sys.argv[2]
    target_dir = sys.argv[3]
    if not start_package_dirs or not proj_dir or not target_dir:
        logging.error('Analyse Java packages or project dir or target UT directory is empty')
        sys.exit(-1)
    ut_gen(start_package_dirs, proj_dir, target_dir, lambda x: 'WdkCartService' in x or
                                                               'WdkCartConfirmService' in x or
                                                               'WDKCartFuseService' in x or
                                                               'WdkCartHgService' in x or
                                                               'WdkCartReadService' in x or
                                                               'WdkCartWriteService' in x)


if __name__ == '__main__':
    main()
