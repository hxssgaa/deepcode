# coding=utf-8
import logging
import os
import re

from collections import OrderedDict

CODE_COMMENT_REGEX = re.compile(r'/\*.*?\*/')
GENERICS_REGEX = re.compile(r'[a-zA-Z]*<(.*?)>')
QUOTE_REGEX = re.compile(r'"(.*?)"')
SINGLE_QUOTE_REGEX = re.compile(r'\'(.*?)\'')
BRACKET_REGEX = re.compile(r'\((.*?)\)')
METHOD_LINE_SPLIT_REGEX = re.compile(r'[^a-zA-Z0-9_.\[\]]')
QUOTE_SEMICOLON_PLACE_HOLDER = 'QUOTE_SEMICOLON_PLACE_HOLDER'
QUOTE_LEFT_BRACKET_PLACE_HOLDER = 'QUOTE_LEFT_BRACKET_PLACE_HOLDER'
QUOTE_RIGHT_BRACKET_PLACE_HOLDER = 'QUOTE_RIGHT_BRACKET_PLACE_HOLDER'
GENERICS_COMMA_PLACE_HOLDER = 'GENERICS_COMMA_PLACE_HOLDER'
SUPPORTED_JAVA_METHOD_MODIFIERS = {'public', 'private', 'static', 'protected', 'abstract', 'final', 'synchronized'}
PRIMITIVE_TYPE = {'boolean', 'byte', 'char', 'short', 'int', 'long', 'float', 'double'}
BASIC_TYPE = PRIMITIVE_TYPE | {
    'String', 'Boolean', 'Byte', 'Char', 'Short', 'Integer', 'Long', 'Float', 'Double', 'Object', 'Map', 'List',
    'Collection'
}
JAVA_KEY_WORDS = {'abstract', 'continue', 'for', 'new', 'switch', 'assert', 'default', 'goto', 'package',
                  'synchronized', 'boolean', 'do', 'if', 'private', 'this', 'break', 'double', 'implements',
                  'protected', 'throw', 'byte', 'else', 'import', 'public', 'throws', 'case', 'enum',
                  'instanceof', 'return', 'transient', 'catch', 'extends', 'int', 'short', 'try', 'char',
                  'final', 'interface', 'static', 'void', 'class', 'finally', 'long', 'volatile', 'const',
                  'float', 'native', 'super', 'while', 'null', 'true', 'false'}


# TODO: inner class support, now the method would be parsed only to the main class in a Java class file.
# TODO: Python 3 support.

class JavaMethodEntity(object):
    def __init__(self, package=None, class_name=None, method_types=list(), ret_type=None,
                 method_name=None, params=None, throws=list(), method_body=None, annotations=list()):
        if params is None:
            params = dict()
        self.package = package  # Package name of the class of this method
        self.class_name = class_name  # Class name of the class of this method
        self.method_types = method_types  # Method modifiers
        self.ret_type = ret_type  # Return type of this method
        self.method_name = method_name  # Method name.
        self.params = params  # Method params
        self.throws = throws  # Method throws
        self.method_body = method_body  # Body of this method
        self.annotations = annotations  # Method annotations


class JavaClassEntity(object):

    def __init__(self, package=None, name=None, class_type=None, class_package_map=None, parent=None, fields=list(),
                 interfaces=list(), methods=list()):
        self.package = package  # Package name
        self.name = name  # Class name
        self.class_type = class_type  # Class type, 0 is normal Java class, 1 is Java interface
        self.class_package_map = class_package_map  # The class-package map imported by this class
        self.parent = parent  # Parent class name
        self.fields = fields  # Private or public fields class name
        self.interfaces = interfaces  # Interface names implemented by this class
        self.methods = methods  # Method entities of this class.


def _is_valid_java_file(file_dir):
    return os.path.isfile(file_dir) and file_dir.endswith('.java')


def _is_package_line(line):
    if not line:
        return False
    line = line.strip()
    return line.startswith('package') and line.endswith(';')


def _is_import_line(line):
    if not line:
        return False
    line = line.strip()
    return line.startswith('import') and line.endswith(';')


def _is_class_line(line):
    if not line:
        return False
    line = line.strip()
    line = QUOTE_REGEX.sub('', line)
    return (line.startswith('public ') or line.startswith('class ') or line.startswith('abstract')
            or line.startswith('final') or line.startswith('interface ') or line.startswith('enum ')) \
           and ('class' in line or 'interface' in line or 'enum' in line)


def _is_non_final_static_spring_field_line(line):
    if not line:
        return False
    line = GENERICS_REGEX.sub(lambda x: x.group().replace(' ', ''), line).strip()
    if '=' in line:
        return _is_non_final_static_spring_field_line('%s;' % line[:line.index('=')])
    # TODO：support static and final types.
    return (line.startswith('public') or line.startswith('private')) \
           and 'static ' not in line and 'final ' not in line and ('(' or ')') not in line and line.endswith(';')


def _is_declare_type(s):
    if not s:
        return False
    s = s.replace('[]', '').strip()
    if not s:
        return False
    return (s[0].isupper() and s.isalnum()) or s in PRIMITIVE_TYPE


def _is_declare_var(s):
    if not s:
        return False
    s = s.replace('[]', '').replace('.', '').strip()
    return not _is_declare_type(s) and s.isalnum() and s[0].islower() and s not in JAVA_KEY_WORDS


def _is_method_name(s):
    if not s:
        return False
    s = s.strip()
    return s.isalnum() and s[0].isalpha() and s[0].islower() and s not in JAVA_KEY_WORDS


def clear_generics(s):
    if not s or '<' not in s:
        return s
    left = 0
    res = []
    for e in s:
        if e == '<':
            left += 1
        elif e == '>':
            left -= 1
        if left == 0 and e != '>':
            res.append(e)
    return ''.join(res)


def _clear_quotes(s):
    return SINGLE_QUOTE_REGEX.sub('0', QUOTE_REGEX.sub('0', s))


def _replace_quote_bracket(line):
    line = QUOTE_REGEX.sub(lambda x: x.group().replace('{', QUOTE_LEFT_BRACKET_PLACE_HOLDER)
                           .replace('}', QUOTE_RIGHT_BRACKET_PLACE_HOLDER), line)
    return SINGLE_QUOTE_REGEX.sub(lambda x: x.group().replace('{', QUOTE_LEFT_BRACKET_PLACE_HOLDER)
                                  .replace('}', QUOTE_RIGHT_BRACKET_PLACE_HOLDER), line)


def _complete_generics_package(s, package, class_package_map):
    if not s:
        return s
    if '<' not in s or '>' not in s:
        if s in class_package_map:
            s = '%s.%s' % (class_package_map[s], s)
        return s
    base_class_type = ''.join(s[:s.index('<')])
    generics_class_type = ''.join(s[s.index('<') + 1:s.rindex('>')])
    if '<' in generics_class_type and '>' in generics_class_type:
        left = generics_class_type.index('<')
        right = generics_class_type.index('>')
        center = generics_class_type[left:right + 1].replace(',', GENERICS_COMMA_PLACE_HOLDER)
        generics_class_type = generics_class_type[:left] + center + generics_class_type[right + 1:]
    generics_class_type.replace(',', GENERICS_COMMA_PLACE_HOLDER)
    base_class_type = _complete_generics_package(base_class_type, package, class_package_map)
    generics_class_type = ','.join(
        map(lambda x: _complete_generics_package(x.replace(GENERICS_COMMA_PLACE_HOLDER, ','), package,
                                                 class_package_map), generics_class_type.split(','))
    )
    return '%s<%s>' % (base_class_type, generics_class_type)


def _parse_method_line(line, class_package_map, package, class_type):
    if not line or '\'' in line or '"' in line or '=' in line or class_type is None:
        return None
    line = GENERICS_REGEX.sub(lambda x: x.group().replace(' ', '').replace(',', GENERICS_COMMA_PLACE_HOLDER),
                              line).strip()

    if class_type == 1:
        if line[-1] != ';':
            return None
        line = line[:-1]

    # Parse method params
    params_m = BRACKET_REGEX.search(line)
    if not params_m:
        return None
    params = map(str.strip, params_m.group(1).split(','))
    params = map(lambda x: map(lambda y: y.replace(GENERICS_COMMA_PLACE_HOLDER, ','), x.split()), params)
    params = filter(lambda x: x, params)
    for p in params:
        if len(p) != 2:
            return None
    params = map(lambda x: (x[0], x[1]), params)  # Transfer to the tuple params.
    params = map(lambda x: (_complete_generics_package(x[0], package, class_package_map), x[1]), params)
    params_dict = OrderedDict()
    for e in params:
        params_dict[e[1]] = e[0]
    params = params_dict

    # Parse method threw exceptions
    filter_quote_line = QUOTE_REGEX.sub('', line)
    filter_quote_line = SINGLE_QUOTE_REGEX.sub('', filter_quote_line)
    throws = []
    if 'throws' in filter_quote_line:
        throws = ''.join(filter_quote_line[filter_quote_line.index('throws') + 6:]).replace('{', '').split(',')
        throws = map(str.strip, throws)
        if '{' in filter_quote_line:
            line = '%s%s' % (line[:line.index('throws')], line[line.rindex('{'):])
        else:
            line = line[:line.index('throws')]

    line = BRACKET_REGEX.sub('', line).replace('{', '').strip()
    line_spt = line.split()
    if len(line_spt) < 2 or len(line_spt) > 6:
        return None
    # In case of JAVA constructors
    if len(line_spt) == 2 and line_spt[-2] in SUPPORTED_JAVA_METHOD_MODIFIERS:
        return None
    method_modifiers = set(line_spt[:-2]) if len(line_spt) > 2 else set()
    # Check if all modifiers are supported
    if len(method_modifiers & SUPPORTED_JAVA_METHOD_MODIFIERS) != len(method_modifiers):
        return None
    method_ret_type, method_name = line_spt[-2].replace(GENERICS_COMMA_PLACE_HOLDER, ','), line_spt[-1]
    method_ret_type = _complete_generics_package(method_ret_type, package, class_package_map)

    # Check valid return type and method name
    if not method_ret_type.replace('<', '').replace('>', '').replace('[', '') \
            .replace(']', '').replace(',', '').replace('.', '').isalnum() or not method_name.isalnum():
        return None
    return method_modifiers, method_ret_type, method_name, params, throws


def build_java_class_key(package_name, class_name):
    if not package_name or not class_name:
        logging.error('package name and class name shouldn\'t be empty')
        return None
    return '%s.%s' % (package_name, class_name)


def get_dir_java_files(directory):
    if not directory or not os.path.exists(directory) or not os.path.isdir(directory):
        return []
    res = []
    for f in os.listdir(directory):
        sub_dir = os.path.join(directory, f)
        if os.path.isdir(sub_dir) and 'src/test/java' not in sub_dir:
            sub_res = get_dir_java_files(sub_dir)
            if sub_res:
                res += sub_res
            continue
        if not _is_valid_java_file(sub_dir):
            continue
        res.append(sub_dir)
    return res


def _get_full_class_name(class_name, class_package_map, package):
    return '%s.%s' % (class_package_map[class_name], class_name) if class_name in class_package_map \
        else ('%s.%s' % (package, class_name))


def _clear_code_comment(lines):
    res = []
    doc_start_pos = (-1, -1)
    for i, e in enumerate(lines):
        e = e.strip()
        e = CODE_COMMENT_REGEX.sub('', e)
        if '/*' in e:
            doc_start_pos = (i, e.index('/*'))
            res.append(''.join(e[:doc_start_pos[1]]))
        if '*/' in e:
            res.append(''.join(e[e.index('*/') + 2:]))
            doc_start_pos = (-1, -1)
            continue
        if doc_start_pos != (-1, -1):
            continue
        res.append(e)
    res = map(lambda x: x[:x.index('//')] if '//' in x else x, res)
    return res


def _format_code_lines_helper(lines):
    res = []
    if not lines:
        return res
    left_bracket = 0
    bracket_s = ''
    for i, e in enumerate(lines):
        e = e.strip()
        e_tmp = QUOTE_REGEX.sub(lambda x: x.group()
                                .replace(';', QUOTE_SEMICOLON_PLACE_HOLDER)
                                .replace('(', QUOTE_LEFT_BRACKET_PLACE_HOLDER)
                                .replace(')', QUOTE_RIGHT_BRACKET_PLACE_HOLDER), e)
        if (_is_import_line(e_tmp) and e_tmp.count(';') > 1 and ';' in e_tmp) or (
                '{' not in e_tmp and 'if' not in e_tmp and '(' not in e_tmp and ')' not in e_tmp
                and 'else' not in e_tmp and ';' in e_tmp and e_tmp.count(';') > 1):
            e_spt = filter(lambda x: x.strip(), e_tmp.split(';'))
            e_spt = map(lambda x: x + ';', e_spt)
            e_spt = map(lambda x:
                        x.replace(QUOTE_SEMICOLON_PLACE_HOLDER, ';')
                        .replace(QUOTE_LEFT_BRACKET_PLACE_HOLDER, '(')
                        .replace(QUOTE_RIGHT_BRACKET_PLACE_HOLDER, ')'), e_spt)
            e_spt = map(str.strip, e_spt)
            res += e_spt
            i += 1
            continue
        left_bracket += e_tmp.count('(')
        left_bracket -= e_tmp.count(')')
        if left_bracket > 0:
            bracket_s += e
        elif left_bracket == 0:
            if bracket_s:
                res.append(bracket_s.strip() + e)
                bracket_s = ''
            else:
                res.append(e)
    lines = filter(lambda x: x.strip(), res)
    res = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if index < len(lines) - 1:
            next_line = lines[index + 1]
            if line.endswith('[') or (next_line.startswith('.') and not line.endswith(';')):
                res.append(line + next_line)
                index += 2
                continue
        res.append(line)
        index += 1
    return res


def _format_code_lines(lines):
    """
    Clear the code comment and format the code into multiple lines if ; occur more than once in one line.

    :param lines: code lines
    :return: formatted code lines
    """
    lines = _clear_code_comment(lines)
    lines = _format_code_lines_helper(lines)
    return lines


def _get_java_class_entity_methods(lines, class_package_map, package, class_name, class_type):
    if not lines or not package or not class_name:
        return []
    res = []
    method = JavaMethodEntity(package=package, class_name=class_name)
    body = []
    left_bracket = 0
    for line in lines:
        line = line.strip()
        parsed = _parse_method_line(line, class_package_map, package, class_type)
        l_tmp = _replace_quote_bracket(line)
        if left_bracket > 0 or parsed:
            left_bracket += l_tmp.count('{')
            left_bracket -= l_tmp.count('}')
        if parsed:
            method.method_types = parsed[0]
            method.ret_type = parsed[1]
            method.method_name = parsed[2]
            method.params = parsed[3]
            method.throws = parsed[4]
            if '{' in line and line[-1] != '{':
                start = line.index('{') + 1
                end = line.index('}') if '}' in line else len(line)
                s = line[start:end].strip()
                if s:
                    body.append(s)
        elif left_bracket > 0:
            body.append(line)
        if left_bracket == 0 and method.method_name:
            method.method_body = {'raw': body}
            res.append(method)
            body = []
            method = JavaMethodEntity(package=package, class_name=class_name)
    return res


def _get_java_class_entity(file_name, class_packages):
    if not file_name or not os.path.isfile(file_name):
        return None
    with open(file_name) as f:
        lines = f.readlines()
    lines = _format_code_lines(lines)
    entity = JavaClassEntity()

    index = 0
    # Find package name
    for l in lines:
        if _is_package_line(l):
            entity.package = l.replace('package', '').replace(';', '').strip()
            break
        index += 1

    class_package_map = {}
    for l in lines[index:]:
        if _is_import_line(l):
            l = l.replace('import', '').replace(';', '').strip()
            l_spt = l.split('.')
            if l_spt[-1] == '*':
                base_package = '.'.join(l_spt[:-1])
                match_packages = filter(lambda x: x.startswith(base_package), class_packages)
                match_packages_map = {e.split('.')[-1]: '.'.join(e.split('.')[:-1]) for e in match_packages}
                class_package_map.update(match_packages_map)
            else:
                class_package_map[l_spt[-1]] = '.'.join(l_spt[:-1])
        if _is_class_line(l):
            break
        index += 1
    for e in ['List', 'Map', 'Collection', 'ArrayList', 'Set']:
        if e not in class_package_map:
            class_package_map[e] = 'java.util'

    # Add local packages import
    if entity.package:
        match_packages = filter(lambda x: x.startswith(entity.package), class_packages)
        match_packages_map = {e.split('.')[-1]: '.'.join(e.split('.')[:-1]) for e in match_packages}
        class_package_map.update(match_packages_map)
    entity.class_package_map = class_package_map

    # Find class name, parent class name and its' implemented interfaces.
    for l in lines[index:]:
        if _is_class_line(l):
            # We just ignore the generics here, because it's useless now.
            t = clear_generics(l).replace('{', '').split()
            if 'class' in t:
                class_index = t.index('class')
                if class_index != len(t):  # Check index boundary
                    entity.name = t[class_index + 1]
                    entity.class_type = 0
            elif 'interface' in t:
                interface_index = t.index('interface')
                if interface_index != len(t):
                    entity.name = t[interface_index + 1]
                    entity.class_type = 1
            elif 'enum' in t:
                enum_index = t.index('enum')
                if enum_index != len(t):
                    entity.name = t[enum_index + 1]
                    entity.class_type = 2
            if 'extends' in t:
                extends_index = t.index('extends')
                if extends_index != len(t):
                    entity.parent = _get_full_class_name(t[extends_index + 1], class_package_map, entity.package)
            if 'implements' in t:
                imp_index = t.index('implements')
                imp_name_line = ' '.join(t[imp_index + 1:])
                imp_names = map(str.strip, imp_name_line.split(','))
                imp_names = map(lambda x: _get_full_class_name(x, class_package_map, entity.package), imp_names)
                entity.interfaces = imp_names
            break
        index += 1

    # Find private and public non-static and non-final fields
    entity.fields = {}
    for l in lines[index:]:
        if _is_non_final_static_spring_field_line(l):
            t = l.strip().replace(';', '')
            eq = None
            for i, c in enumerate(t):
                if ('"' or '\'') == c:
                    break
                if '=' == c:
                    eq = ''.join(t[i + 1:])
                    t = ''.join(t[:i]).strip()
                    break
            t = GENERICS_REGEX.sub(lambda x: x.group().replace(' ', ''), t)
            t = t.split()
            field_class = '%s.%s' % (class_package_map[t[-2]], t[-2]) if t[-2] in class_package_map else t[-2]
            field_name = t[-1]
            entity.fields[field_name] = (field_class, eq)

    # Find methods of this class.
    entity.methods = _get_java_class_entity_methods(lines[index:], class_package_map, entity.package, entity.name,
                                                    entity.class_type)

    # if class has no name, return None
    if not entity.name:
        return None
    return entity


def _build_class_dep_chain_helper(entity, class_map, impl_map, visited):
    if not entity or not entity.name or not class_map:
        return {}
    key = build_java_class_key(entity.package, entity.name)
    if key in visited:
        return {}
    visited.add(key)
    if entity.class_type == 1:
        if key not in impl_map:
            visited.remove(key)
            return {}
        impl_entity = impl_map[key]
        res = _build_class_dep_chain_helper(class_map[impl_entity[0]], class_map, impl_map, visited)
        visited.remove(key)
        return res
    dep = {}
    res = {key: dep}
    for _, (field, _) in entity.fields.items():
        m = GENERICS_REGEX.match(field)
        if m:
            field = m.group(1)
        if field in class_map:
            field_entity = class_map[field]
            field_dep = _build_class_dep_chain_helper(field_entity, class_map, impl_map, visited)
            dep[field] = field_dep
        else:
            dep[field] = {}
    visited.remove(key)
    return res


def _build_class_dep_chain(entity, class_map, impl_map):
    return _build_class_dep_chain_helper(entity, class_map, impl_map, set())


def _get_dependency_by_package(start_package, class_map, impl_map):
    if not start_package or not class_map or not os.path.isdir(start_package):
        return {}
    res = {}
    for sub_dir in get_dir_java_files(start_package):
        key = get_java_class_entity_key_by_directory(sub_dir)
        if key not in class_map:
            logging.error('%s not in class_map, dir is: %s' % (key, sub_dir))
            return None
        entity = class_map[key]
        res[key] = _build_class_dep_chain(entity, class_map, impl_map)
    return res


def _get_proj_class_packages(proj_dir):
    if not proj_dir or not os.path.exists(proj_dir) or not os.path.isdir(proj_dir):
        return []
    res = []
    for sub_dir in get_dir_java_files(proj_dir):
        if 'src/main/java' not in sub_dir:
            continue
        res.append('.'.join(sub_dir[sub_dir.index('src/main/java') + 14:].replace('.java', '').split(os.sep)))
    return res


def get_java_class_entity_key_by_directory(directory):
    entity = _get_java_class_entity(directory, [])
    if not entity:
        return None
    return build_java_class_key(entity.package, entity.name)


def get_proj_class_map(proj_dir):
    if not proj_dir or not os.path.exists(proj_dir) or not os.path.isdir(proj_dir):
        return {}
    class_packages = _get_proj_class_packages(proj_dir)
    res = {}
    for sub_dir in get_dir_java_files(proj_dir):
        class_entity = _get_java_class_entity(sub_dir, class_packages)
        if not class_entity:
            continue
        key = build_java_class_key(class_entity.package, class_entity.name)
        res[key] = class_entity
    return res


def _find_vars_and_methods(line, line_spt, entity):
    if not line or not line_spt:
        return {}
    res = {}
    for spt in line_spt:
        line = line.replace(spt, '^^^', 1)
    separated = line.split('^^^')[1:]
    var_method_name_map = {'.'.join(e.split('.')[:-1]): e.split('.')[-1] for e in line_spt
                           if '.' in e and _is_method_name(e.split('.')[-1])}
    line_spt = map(lambda x: '.'.join(x.split('.')[:-1] if '.' in x else [x]), line_spt)
    for i in range(len(separated)):
        if i < len(separated) - 1 and not separated[i].strip() and _is_declare_type(line_spt[i]) \
                and _is_declare_var(line_spt[i + 1]):
            res[line_spt[i + 1]] = {
                'class_type': line_spt[i],
            }
        elif _is_declare_var(line_spt[i]) and line_spt[i] not in res:
            res[line_spt[i]] = {
                'class_type': '?',
            }
            left_bracket = 1
            end = None
            for j, x in enumerate(separated[i + 1:]):
                left_bracket += x.count('(')
                left_bracket -= x.count(')')
                left_bracket += x.count('{')
                left_bracket -= x.count('}')
                if ')' in x and left_bracket == 0:
                    end = j
                    break
            param_count = 0
            if end is not None:
                left_bracket = 0
                for e in separated[i + 1: end + i + 1]:
                    left_bracket += e.count('(')
                    left_bracket -= e.count(')')
                    left_bracket += e.count('{')
                    left_bracket -= e.count('}')
                    if ',' in e and left_bracket == 0:
                        param_count += 1
                param_count += 1

            if line_spt[i] in var_method_name_map:
                method_name = var_method_name_map[line_spt[i]]
                res[line_spt[i]]['invoke_methods'] = {(method_name, param_count)}
            else:
                entity_method_keys = {(e.method_name, len(e.params)) for e in entity.methods}
                var_key = (line_spt[i], param_count)
                if var_key in entity_method_keys:
                    res[line_spt[i]]['class_type'] = 'Self'
                    res[line_spt[i]]['self_method'] = {var_key}
    return res


def _setup_entity_method_dep_by_method(entity, method):
    if not entity or not method or 'raw' not in method.method_body:
        return
    raw_body = method.method_body['raw']
    local_vars = {}
    external_vars = {}
    self_methods = set()
    for line in raw_body:
        line = clear_generics(_clear_quotes(line)).replace('this.', '')
        for e in '.+-*/,^!&|<>%':
            line = e.join(map(str.strip, line.split(e)))
        line_spt = filter(lambda x: x, re.split(METHOD_LINE_SPLIT_REGEX, line))
        line_spt = [e + line_spt[i + 1] if e.startswith('.') and i < len(line_spt) - 1
                    else e for i, e in enumerate(line_spt)]
        line_spt = filter(lambda x: not x.startswith('.'), line_spt)
        # print(line, line_spt)
        for k, v in _find_vars_and_methods(line, line_spt, entity).items():
            var_class_type = v['class_type']
            var_invoke_methods = v['invoke_methods'] if 'invoke_methods' in v else None

            if var_class_type == '?' and k in method.params:
                var_class_type = method.params[k]
            if var_class_type in entity.class_package_map:
                var_class_type = '%s.%s' % (entity.class_package_map[var_class_type], var_class_type)
            if var_class_type == '?':
                if k in entity.fields:
                    var_class_type = entity.fields[k][0]
                if k not in local_vars:
                    v['class_type'] = var_class_type
                    if k not in external_vars:
                        external_vars[k] = v
                    elif var_invoke_methods:
                        if 'invoke_methods' not in external_vars[k]:
                            external_vars[k]['invoke_methods'] = set()
                        external_vars[k]['invoke_methods'] |= var_invoke_methods
            elif var_class_type == 'Self':
                self_methods |= v['self_method']
            elif k not in external_vars and k not in local_vars:
                v['class_type'] = var_class_type
                local_vars[k] = v
    method.method_body['local_vars'] = local_vars
    method.method_body['external_vars'] = external_vars
    method.method_body['self_methods'] = self_methods


def _setup_entity_method_dep(entity):
    if not entity or not entity.methods:
        return
    for method in entity.methods:
        _setup_entity_method_dep_by_method(entity, method)


def setup_class_map_method_dep(class_map):
    if not class_map:
        return
    for v in class_map.values():
        _setup_entity_method_dep(v)


def get_impl_map(class_map):
    if not class_map:
        return {}
    impl_map = {k: [] for k in class_map.keys()}
    for k, v in class_map.items():
        for e in v.interfaces:
            if e in impl_map:
                impl_map[e] += [k]
    return {k: v for k, v in impl_map.items() if v}


def get_dependency(start_packages, class_map, impl_map):
    if not start_packages or not class_map:
        return {}
    res = {}
    for e in start_packages:
        res.update(_get_dependency_by_package(e, class_map, impl_map))
    return res
