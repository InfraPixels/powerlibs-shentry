#!/usr/bin/env python

from setuptools import setup


setup(
    name="shentry",
    version="0.1.0",
    author="Cléber Zavadniak",
    author_email="contato@cleber.solutions",
    url="https://github.com/cleber-solutions/powerlibs-shentry",
    license="ISC",
    packages=['shentry'],
    entry_points='''
        [console_scripts]
        shentry=shentry:main
    ''',
    keywords=["logging"],
    description="Wrap a program in Sentry",
    python_requires='>=3.6',
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Operating System :: POSIX",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: ISC License (ISCL)",
    ]
)
