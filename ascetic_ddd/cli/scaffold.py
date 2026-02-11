from ascetic_ddd.cli.parser import parse_yaml
from ascetic_ddd.cli.renderer import render_bounded_context


def scaffold(input_path, output_dir, package_name=None):
    model = parse_yaml(input_path)
    files = render_bounded_context(model, output_dir, package_name)
    print("Generated %d files:" % len(files))
    for f in files:
        print("  %s" % f)
