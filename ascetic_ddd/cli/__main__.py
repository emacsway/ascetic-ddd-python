import argparse
import sys

from ascetic_ddd.cli.scaffold import scaffold


def main():
    parser = argparse.ArgumentParser(
        description="ascetic-ddd CLI tools",
    )
    subparsers = parser.add_subparsers(dest='command')

    scaffold_parser = subparsers.add_parser(
        'scaffold',
        help='Generate DDD bounded context from YAML definition',
    )
    scaffold_parser.add_argument(
        '--input', '-i',
        required=True,
        help='Path to domain-model YAML file',
    )
    scaffold_parser.add_argument(
        '--output', '-o',
        required=True,
        help='Output directory for generated code',
    )
    scaffold_parser.add_argument(
        '--package', '-p',
        default=None,
        help='Base package name for imports (e.g. "app.jobs")',
    )
    scaffold_parser.add_argument(
        '--templates', '-t',
        default=None,
        help='Custom templates directory (overrides built-in templates)',
    )

    args = parser.parse_args()
    if args.command == 'scaffold':
        scaffold(args.input, args.output, args.package, args.templates)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
