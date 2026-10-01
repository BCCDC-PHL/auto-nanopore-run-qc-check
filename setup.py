from setuptools import setup, find_namespace_packages

setup(
    name='auto-nanopore-run-qc-check',
    version='0.1.0',
    packages=find_namespace_packages(),
    entry_points={
        "console_scripts": [
            "auto-nanopore-run-qc-check = auto_nanopore_run_qc_check.__main__:main",
        ]
    },
    scripts=[],
    package_data={
        "auto_nanopore_run_qc_check": ["templates/*.html"],
    },
    python_requires='>=3.11',
    install_requires=[
        'requests~=2.32',
        'jinja2~=3.1',
    ],
    description='Automated checking of run-level QC metrics for nanopore sequencing runs.',
    url='https://github.com/BCCDC-PHL/auto-nanopore-run-qc-check',
    author='Dan Fornika',
    author_email='dan.fornika@bccdc.ca',
    include_package_data=True,
    keywords=[],
    zip_safe=False
)
