from ascetic_ddd.cli.scaffold.parser import parse_yaml
from ascetic_ddd.cli.scaffold.renderer import (
    ast_render_bounded_context,
    render_bounded_context,
)


def scaffold(input_path, output_dir, package_name=None,
             templates_dir=None):
    model = parse_yaml(input_path)
    files = render_bounded_context(model, output_dir, package_name,
                                   templates_dir)
    print("Generated %d files:" % len(files))
    for f in files:
        print("  %s" % f)


def ast_scaffold(input_path, output_dir, package_name=None,
                 templates_dir=None):
    model = parse_yaml(input_path)
    files = ast_render_bounded_context(model, output_dir, package_name,
                                       templates_dir)
    print("Generated %d files:" % len(files))
    for f in files:
        print("  %s" % f)
