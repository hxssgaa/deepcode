from git import Repo


def _check_line_startswith(line, s):
    if not line:
        return False
    if line.startswith(s):
        return True
    return False


def _is_file_diff_line(line):
    return _check_line_startswith(line, 'diff --git ')


def _is_change_start_line(line):
    return _check_line_startswith(line, '@@') and line.count('@@') >= 2


def _is_new_added_line(line):
    return _check_line_startswith(line, '+') and (len(line) == 1 or line[1] != '+')


def _is_new_deleted_line(line):
    return _check_line_startswith(line, '-') and (len(line) == 1 or line[1] != '-')


def _process_diff_lines(lines):
    if not lines:
        return {}
    res = {}
    change_file_name = None
    temp_index_line = 0
    for l in lines:
        if _is_file_diff_line(l):
            change_file_name = l.split()[3].split('/', 1)[-1]
            res[change_file_name] = []
            continue
        if _is_change_start_line(l):
            temp_index_line = int(''.join(l.split()[2].split(',')[0][1:]))
            continue
        if _is_new_deleted_line(l):
            continue
        if _is_new_added_line(l):
            res[change_file_name] += [temp_index_line]
        if temp_index_line > 0:
            temp_index_line += 1
    return res


def diff_against_master(branch_name, proj_dir):
    if not branch_name or not proj_dir:
        return {}
    repo = Repo(proj_dir)
    diff = repo.git.diff('master', branch_name).encode('utf-8')
    if not diff:
        return {}
    return _process_diff_lines(diff.split('\n'))
