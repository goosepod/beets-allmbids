"""Install a built wheel and verify Beets loads it outside the source checkout."""
import argparse
import os
from pathlib import Path
import site
import subprocess
import tempfile
import venv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dist', type=Path, help='directory containing exactly one plugin wheel')
    args = parser.parse_args()
    wheels = list(args.dist.resolve().glob('beets_allmbids-*.whl'))
    if len(wheels) != 1:
        raise ValueError('Expected exactly one beets-allmbids wheel')
    with tempfile.TemporaryDirectory(prefix='allmbids-wheel-') as directory:
        root = Path(directory)
        environment = root / 'venv'
        # Reuse test dependencies, but install this artifact into its own site-packages.
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        env = dict(os.environ, BEETSDIR=str(root / 'config'))
        env.pop('PYTHONPATH', None)
        # Nested venvs inherit the base interpreter, not the caller's venv.
        # Add dependency directories explicitly, without executing the caller's
        # editable-install .pth files or including the source checkout.
        result = subprocess.run([str(python), '-c', 'import sysconfig; print(sysconfig.get_path("purelib"))'],
                                cwd=root, env=env, capture_output=True, text=True, check=True)
        dependency_file = Path(result.stdout.strip()) / 'allmbids_smoke_dependencies.pth'
        dependency_file.write_text('\n'.join(site.getsitepackages()) + '\n', encoding='utf-8')
        subprocess.run([str(python), '-m', 'pip', 'install', '--force-reinstall', '--no-deps', str(wheels[0])],
                       cwd=root, env=env, check=True)
        script = (
            'from pathlib import Path; import beetsplug.allmbids as plugin; '
            f'root = Path({str(environment)!r}).resolve(); '
            'location = Path(plugin.__file__).resolve(); '
            "print('Installed plugin:', location); "
            "location.relative_to(root)"
        )
        subprocess.run([str(python), '-c', script], cwd=root, env=env, check=True)
        config = root / 'config.yaml'
        config.write_text('plugins: [allmbids]\n', encoding='utf-8')
        result = subprocess.run([str(python), '-m', 'beets', '-c', str(config),
                                 'allmbids', '--help'], cwd=root, env=env,
                                capture_output=True, text=True, check=True)
        if not all(flag in result.stdout for flag in ('--write', '--limit', '--report')):
            raise ValueError('Installed wheel did not expose the complete command')
        print('Installed wheel loads successfully and exposes allmbids --help')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
