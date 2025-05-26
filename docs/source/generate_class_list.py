import importlib
import inspect
import fnmatch
from io import TextIOWrapper


def write_classes(f: TextIOWrapper, patterns: list[str], module_name: str, title: str, description: str = '', exclude: list[str] = []) -> None:

    module = importlib.import_module(module_name)

    classes = [
        name for name, obj in inspect.getmembers(module, inspect.isclass)
        if (obj.__module__ == module_name and
            any(fnmatch.fnmatch(name, pat) for pat in patterns if pat not in exclude) and
            obj.__doc__ and '(Automatic generated stub)' not in obj.__doc__)
    ]

    """Write the classes to the file."""
    f.write(f'## {title}\n\n')
    if description:
        f.write(f'{description}\n\n')

    for cls in classes:
        f.write('```{eval-rst}\n')
        f.write(f'.. autoclass:: {module_name}.{cls}\n')
        f.write('   :members:\n')
        f.write('   :undoc-members:\n')
        f.write('   :show-inheritance:\n')
        f.write('   :inherited-members:\n')
        if title != 'Base classes':
            f.write('   :exclude-members: select\n')
        f.write('```\n\n')


def write_functions(f: TextIOWrapper, patterns: list[str], module_name: str, title: str, description: str = '', exclude: list[str] = []) -> None:

    module = importlib.import_module(module_name)

    classes = [
        name for name, obj in inspect.getmembers(module, inspect.isfunction)
        if (obj.__module__ == module_name and
            any(fnmatch.fnmatch(name, pat) for pat in patterns if pat not in exclude))
    ]

    """Write the classes to the file."""
    f.write(f'## {title}\n\n')
    if description:
        f.write(f'{description}\n\n')

    for func in classes:
        if not func.startswith('_'):
            f.write('```{eval-rst}\n')
            f.write(f'.. autofunction:: {module_name}.{func}\n')
            f.write('```\n\n')


with open('docs/source/modules.md', 'w') as f:
    f.write('# Pyladoc classes, functions and submodules\n\n')
    write_classes(f, ['DocumentWriter'], 'pyladoc', title='DocumentWriter Class')
    write_functions(f, ['*'], 'pyladoc', title='Functions')
    write_functions(f, ['*'], 'pyladoc.latex', title='Submodule latex')
