# Powerlibs: shentry

**Shentry** is a single-file Python script which will run the wrapped
command and, if it fails, post an event to Sentry. By default, if the
wrapped script succeeds (exists with code 0), stdout/stderr are squashed,
similarly to [shuck](https://github.com/thwarted/shuck) or
[chronic](https://joeyh.name/code/moreutils/). It also always exits with
status 0 if events are able to be sent to Sentry.

It reads its configuration from the environment variable `SHELL_SENTRY_DSN`
and, if such a variable is found, removes it from the environment before
calling the wrapped program. If no DSN can be found, the wrapped will have
normal behavior (stdout/stderr will go to their normal file descriptors,
exit code will be passed through, etc).

This software requires Python 3.6+.


## Installation

    pip install 'git+https://github.com/InfraPixels/powerlibs-shentry.git'

## Usage

    shentry -c <command> [arguments]

## License

This software is licensed under the ISC License, the full text of which
can be found at [LICENSE.txt](LICENSE.txt).
